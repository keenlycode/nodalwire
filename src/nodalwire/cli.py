"""Foreground service and bounded one-shot command input/output primitives."""

import asyncio
import base64
import binascii
import json
import math
import os
import signal
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO

from cyclopts import App

from .config import RelayConfig, load_config
from .credentials import validate_token
from .protocol import valid_name
from .server import Relay

app = App(help="Run the loopback-only byte relay for trusted local applications.")


class CLIInputError(ValueError):
    """Safe input error; never contains supplied credential or payload material."""


class CLIOutputLimit(ValueError):
    """Explicit cutoff, not a claim that an outstanding request had no effect."""


def _bounded_read(source: BinaryIO, max_bytes: int) -> bytes:
    if type(max_bytes) is not int or not 0 <= max_bytes <= 16 * 1024 * 1024:
        raise CLIInputError("invalid input byte limit")
    chunks = []
    remaining = max_bytes + 1
    while remaining:
        part = source.read(remaining)
        if not part:
            break
        chunks.append(part)
        remaining -= len(part)
    result = b"".join(chunks)
    if len(result) > max_bytes:
        raise CLIInputError("input exceeds byte limit")
    return result


def _read_payload(path: Path | None, max_bytes: int) -> bytes:
    try:
        if path is None:
            return _bounded_read(sys.stdin.buffer, max_bytes)
        with path.open("rb") as source:
            return _bounded_read(source, max_bytes)
    except OSError:
        raise CLIInputError("cannot read input") from None


def _env_token(variable: str | None, *, required: bool = False) -> str | None:
    if variable is None:
        if required:
            raise CLIInputError("credential environment variable required")
        return None
    token = os.environ.get(variable)
    try:
        validate_token(token)
    except ValueError:
        raise CLIInputError("credential environment variable is missing or malformed") from None
    return token


def _positive_deadline(timeout: float) -> float:
    if type(timeout) not in (int, float) or not 0 < timeout <= 3600 or not math.isfinite(timeout):
        raise CLIInputError("deadline must be finite and between zero and 3600 seconds")
    return float(timeout)


def _message_event(message, *, event: str = "message") -> dict:
    return {
        "event": event,
        "network": message.network,
        "sender": message.sender,
        "payload": base64.b64encode(message.payload).decode("ascii"),
    }


@dataclass(frozen=True)
class _Incoming:
    network: str
    sender: str
    payload: bytes


def _decode_incoming(data: bytes, max_payload: int) -> _Incoming:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate input key")
            result[key] = value
        return result

    try:
        item = json.loads(data, object_pairs_hook=unique)
        if not isinstance(item, dict) or set(item) != {"event", "network", "sender", "payload"}:
            raise ValueError("invalid message fields")
        if item["event"] != "message" or not all(
            valid_name(item[key]) for key in ("network", "sender")
        ):
            raise ValueError("invalid message metadata")
        encoded = item["payload"]
        if not isinstance(encoded, str) or len(encoded) > 4 * ((max_payload + 2) // 3):
            raise ValueError("invalid payload length")
        payload = base64.b64decode(encoded, validate=True)
        if len(payload) > max_payload or base64.b64encode(payload).decode("ascii") != encoded:
            raise ValueError("invalid payload encoding")
    except (ValueError, TypeError, UnicodeError, binascii.Error, RecursionError):
        raise CLIInputError("invalid incoming message JSON") from None
    return _Incoming(item["network"], item["sender"], payload)


class _OutputBudget:
    """Bound JSON output explicitly; stdout errors never imply request rollback."""

    def __init__(self, *, max_count: int, max_bytes: int, stream: TextIO | None = None):
        if type(max_count) is not int or not 1 <= max_count <= 1024:
            raise CLIInputError("invalid output count limit")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 16 * 1024 * 1024:
            raise CLIInputError("invalid output byte limit")
        self.max_count = max_count
        self.max_bytes = max_bytes
        self.count = 0
        self.bytes = 0
        self.stream = sys.stdout if stream is None else stream

    def emit(self, event: dict) -> None:
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n"
        size = len(line.encode("utf-8"))
        if self.count >= self.max_count or self.bytes + size > self.max_bytes:
            raise CLIOutputLimit("output limit reached; request outcome may be uncertain")
        self.stream.write(line)
        self.stream.flush()
        self.count += 1
        self.bytes += size


async def _serve(config: RelayConfig) -> None:
    relay = Relay(config)
    endpoint = await relay.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    runner = asyncio.create_task(relay.run())
    waiter = asyncio.create_task(stop.wait())
    print(endpoint, flush=True)
    try:
        completed, _ = await asyncio.wait([runner, waiter], return_when=asyncio.FIRST_COMPLETED)
        if runner in completed:
            await runner  # Surface a service failure, not a false successful shutdown.
    finally:
        runner.cancel()
        waiter.cancel()
        await asyncio.gather(runner, waiter, return_exceptions=True)
        await relay.close()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.remove_signal_handler(sig)


@app.default
def main(*, config: Path | None = None) -> None:
    """Start the relay; prints the bound endpoint after native bind succeeds.

    Parameters
    ----------
    config
        Startup cooperative TOML policy. Default: open admission on loopback.
    """
    asyncio.run(_serve(load_config(config) if config is not None else RelayConfig()))
