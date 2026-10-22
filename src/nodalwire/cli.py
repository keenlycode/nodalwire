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


async def _request_with_events(
    node,
    destination: str,
    payload: bytes,
    *,
    network: str,
    timeout: float,
    output: _OutputBudget,
):
    """Use the public client API; preserve ordinary inbox data at a bounded cutoff."""
    request = asyncio.create_task(
        node.request(destination, payload, network=network, timeout=timeout)
    )
    receiver = asyncio.create_task(node.receive())
    output_failed = False
    try:
        while True:
            done, _ = await asyncio.wait((request, receiver), return_when=asyncio.FIRST_COMPLETED)
            if receiver in done:
                message = receiver.result()
                try:
                    output.emit(_message_event(message))
                except (CLIOutputLimit, OSError):
                    output_failed = True
                    raise
                receiver = None
            if request in done:
                return request.result()
            if receiver is None:
                receiver = asyncio.create_task(node.receive())
    finally:
        request.cancel()
        if receiver is not None:
            receiver.cancel()
        results = await asyncio.gather(
            request, *(() if receiver is None else (receiver,)), return_exceptions=True
        )
        if not output_failed:
            # receive() may return already-owned ordinary DATA despite cancellation.
            if receiver is not None and not isinstance(results[-1], BaseException):
                output.emit(_message_event(results[-1]))
            while (message := node.receive_nowait()) is not None:
                output.emit(_message_event(message))


def _admin_arguments(
    operation: str,
    *,
    network: str | None = None,
    member: str | None = None,
    protected: bool | None = None,
    credential: str | None = None,
) -> dict:
    shapes = {
        "config.get": (),
        "network.list": (),
        "network.get": ("network",),
        "network.create": ("network", "credential"),
        "network.update": ("network", "protected", "credential"),
        "network.rotate": ("network", "credential"),
        "network.delete": ("network",),
        "member.list": ("network",),
        "member.remove": ("network", "name"),
        "admin.rotate": ("credential",),
    }
    if operation not in shapes:
        raise CLIInputError("unknown administrative operation")
    supplied = {
        "network": network,
        "name": member,
        "protected": protected,
        "credential": credential,
    }
    arguments = {key: value for key, value in supplied.items() if value is not None}
    if arguments.keys() - set(shapes[operation]):
        raise CLIInputError("unexpected administrative argument")
    for key in ("network", "name"):
        if key in shapes[operation] and not valid_name(arguments.get(key)):
            raise CLIInputError("administrative name argument required")
    if "protected" in shapes[operation] and type(protected) is not bool:
        raise CLIInputError("network update requires explicit protection policy")
    if operation in {"network.rotate", "admin.rotate"} and credential is None:
        raise CLIInputError("new credential environment variable required")
    if credential is not None:
        try:
            validate_token(credential)
        except ValueError:
            raise CLIInputError("invalid new credential format") from None
    if operation == "network.update" and not protected and credential is not None:
        raise CLIInputError("open network cannot have a join credential")
    return arguments


def _admin_revision(operation: str, expected_revision: int | None) -> None:
    reads = {"config.get", "network.list", "network.get", "member.list"}
    if operation in reads:
        if expected_revision is not None:
            raise CLIInputError("read operation does not accept expected revision")
    elif type(expected_revision) is not int or not 0 <= expected_revision <= (1 << 53) - 1:
        raise CLIInputError("mutation requires an explicit valid expected revision")


async def _peer_operation(
    node,
    operation: str,
    *,
    destination: str | None,
    payload: bytes,
    network: str,
    credential: str | None,
    timeout: float,
    count: int,
    output: _OutputBudget,
    incoming: _Incoming | None = None,
) -> dict:
    if operation not in {"send", "receive", "request", "reply"}:
        raise CLIInputError("unknown client operation")
    if not valid_name(network):
        raise CLIInputError("invalid selected network")
    if operation in {"send", "request"} and not valid_name(destination):
        raise CLIInputError("destination required")
    if type(count) is not int or not 1 <= count <= 1024:
        raise CLIInputError("receive count must be between one and 1024")
    if operation == "reply":
        if incoming is None:
            raise CLIInputError("incoming request metadata required")
        network = incoming.network
    async with asyncio.timeout(_positive_deadline(timeout)):
        # Even open nondefault networks require a new explicit join per invocation.
        await node.join(network, credential, timeout=timeout)
        if operation == "send":
            await node.send(destination, payload, network=network, timeout=timeout)
            return {
                "event": "accepted",
                "network": network,
                "recipient": destination,
                "meaning": "native_queue_acceptance_only",
            }
        if operation == "reply":
            await node.reply(incoming, payload, timeout=timeout)
            return {
                "event": "accepted",
                "network": network,
                "recipient": incoming.sender,
                "meaning": "native_queue_acceptance_only",
            }
        if operation == "request":
            message = await _request_with_events(
                node, destination, payload, network=network, timeout=timeout, output=output
            )
            return _message_event(message, event="reply")
        for _ in range(count):
            output.emit(_message_event(await node.receive()))
        return {"event": "complete", "received": count}


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
