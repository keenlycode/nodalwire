"""Foreground service and bounded one-shot command input/output primitives."""

import asyncio
import base64
import binascii
import json
import math
import os
import select
import signal
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import BinaryIO, TextIO

from cyclopts import App

from .admin import AdminClient, AdminError
from .client.python import Message, Node
from .config import RelayConfig, load_config
from .config_store import ConfigStore
from .credentials import validate_token
from .protocol import ReceiptTimeout, RelayError, valid_name
from .server import Relay

app = App(
    help=(
        "Loopback relay and bounded one-shot commands. Each client invocation has a new "
        "connection/membership; use Python/Node libraries for persistent use. "
        "Credentials grant permission, not peer-name identity. No automatic retries."
    )
)


class CLIInputError(ValueError):
    """Safe input error; never contains supplied credential or payload material."""


class CLIOutputLimit(ValueError):
    """Explicit cutoff, not a claim that an outstanding request had no effect."""


class CLIReleaseError(Exception):
    """Operation result already emitted; release cannot relabel it no-effect."""

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


async def _join_owned_cleanup(*tasks):
    """Settle only our children without replacing the already-owned outcome.

    Called from finally: pre-selection cancellation/exception still propagates
    after cleanup. Cancellation arriving during cleanup cannot erase a selected
    reply or a receiver result already claimed before its first cancellation.
    """
    task = asyncio.current_task()
    initial_cancels = task.cancelling()
    cleanup = asyncio.gather(*tasks, return_exceptions=True)
    while True:
        try:
            return await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            # Suppress only additional cleanup-time requests, not an active
            # pre-selection cancellation/deadline. Keep outer timeout accounting
            # intact so an earlier deadline still becomes TimeoutError.
            while task.cancelling() > initial_cancels:
                task.uncancel()


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


def _read_fd(fd: int, max_bytes: int, deadline: float) -> bytes:
    if type(max_bytes) is not int or not 0 <= max_bytes <= 16 * 1024 * 1024:
        raise CLIInputError("invalid input byte limit")
    chunks = []
    remaining = max_bytes + 1
    while remaining:
        seconds = deadline - time.monotonic()
        if seconds <= 0 or not select.select([fd], [], [], seconds)[0]:
            raise TimeoutError("input deadline exceeded")
        part = os.read(fd, min(remaining, 65536))
        if not part:
            break
        chunks.append(part)
        remaining -= len(part)
    result = b"".join(chunks)
    if len(result) > max_bytes:
        raise CLIInputError("input exceeds byte limit")
    return result


def _read_payload(path: Path | None, max_bytes: int, *, deadline: float | None = None) -> bytes:
    def read(source):
        if deadline is None:
            return _bounded_read(source, max_bytes)
        return _read_fd(source.fileno(), max_bytes, deadline)

    try:
        if path is None:
            return read(sys.stdin.buffer)
        # O_NONBLOCK prevents an input FIFO from hanging before the deadline read.
        fd = os.open(path, os.O_RDONLY | os.O_NONBLOCK)
        try:
            with os.fdopen(fd, "rb", closefd=False) as source:
                return read(source)
        finally:
            os.close(fd)
    except TimeoutError:
        raise
    except OSError:
        raise CLIInputError("cannot read input") from None


def _timed_write(stream: TextIO, line: str, deadline: float | None) -> None:
    if deadline is None:
        stream.write(line)
        stream.flush()
        return
    try:
        fd = stream.fileno()
    except (AttributeError, OSError):
        stream.write(line)
        stream.flush()
        return
    data = line.encode("utf-8")
    blocking = os.get_blocking(fd)
    os.set_blocking(fd, False)
    try:
        offset = 0
        while offset < len(data):
            seconds = deadline - time.monotonic()
            if seconds <= 0 or not select.select([], [fd], [], seconds)[1]:
                raise TimeoutError("output deadline exceeded")
            try:
                offset += os.write(fd, data[offset : offset + 65536])
            except BlockingIOError:
                continue
    finally:
        os.set_blocking(fd, blocking)


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

    def __init__(
        self,
        *,
        max_count: int,
        max_bytes: int,
        stream: TextIO | None = None,
        deadline: float | None = None,
    ):
        if type(max_count) is not int or not 1 <= max_count <= 1024:
            raise CLIInputError("invalid output count limit")
        if type(max_bytes) is not int or not 1 <= max_bytes <= 16 * 1024 * 1024:
            raise CLIInputError("invalid output byte limit")
        self.max_count = max_count
        self.max_bytes = max_bytes
        self.count = 0
        self.bytes = 0
        self.stream = sys.stdout if stream is None else stream
        self.deadline = deadline

    def emit(self, event: dict) -> None:
        line = json.dumps(event, ensure_ascii=True, separators=(",", ":"), allow_nan=False) + "\n"
        size = len(line.encode("utf-8"))
        if self.count >= self.max_count or self.bytes + size > self.max_bytes:
            raise CLIOutputLimit("output limit reached; request outcome may be uncertain")
        _timed_write(self.stream, line, self.deadline)
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
    task = asyncio.current_task()
    entry_cancels = task.cancelling()
    output_failed = False
    primary = None
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
                request.result()  # Capture a definite request failure before cleanup.
                break
            if receiver is None:
                receiver = asyncio.create_task(node.receive())
    except BaseException as error:
        primary = error
    request.cancel()
    if receiver is not None:
        receiver.cancel()
    results = await _join_owned_cleanup(request, *(() if receiver is None else (receiver,)))
    if not output_failed:
        # receive() may return already-owned ordinary DATA despite cancellation.
        if receiver is not None and not isinstance(results[-1], BaseException):
            output.emit(_message_event(results[-1]))
        while (message := node.receive_nowait()) is not None:
            output.emit(_message_event(message))
    if not isinstance(results[0], BaseException) and (
        primary is None or isinstance(primary, (asyncio.CancelledError, RelayError))
    ):
        # The client may already own a reply but still be joining its children
        # when our wait gets cancelled. Its successful result remains authoritative.
        if isinstance(primary, asyncio.CancelledError):
            while task.cancelling() > entry_cancels:
                task.uncancel()
        return results[0]
    if primary is not None:
        raise primary
    raise results[0]


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
    ready=None,
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
            message = Message(incoming.sender, incoming.payload, incoming.network)
            await node.reply(message, payload, timeout=timeout)
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
        if ready is not None:
            ready()
        for _ in range(count):
            output.emit(_message_event(await node.receive()))
        return {"event": "complete", "received": count}


async def _serve(store: ConfigStore) -> None:
    relay = Relay(store=store)
    endpoint = await relay.start()
    stop = asyncio.Event()
    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, stop.set)
    runner = asyncio.create_task(relay.run())
    waiter = asyncio.create_task(stop.wait())
    try:
        print(endpoint, flush=True)
        _status(
            {
                "event": "serving",
                "endpoint": endpoint,
                "admin_endpoint": relay.admin_endpoint,
                "admin_source": store.admin_source,
            },
            time.monotonic() + 1,
        )
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


def _status(event: dict, deadline: float) -> None:
    _OutputBudget(max_count=1, max_bytes=2 * 1024 * 1024, deadline=deadline).emit(event)


def _execute(action) -> None:
    try:
        action()
        return
    except CLIReleaseError as error:
        event = {
            "error": error.code,
            "outcome": "indeterminate",
            "phase": "release",
            "operation_completed": True,
            "message": "operation result was emitted before release failed; do not blindly retry",
        }
        status = 1
    except AdminError as error:
        event = {"error": error.code, "outcome": error.outcome, "revision": error.revision}
        status = 1
    except CLIInputError as error:
        event = {"error": "invalid_input", "outcome": "no_effect", "message": str(error)}
        status = 2
    except (ReceiptTimeout, TimeoutError):
        event = {
            "error": "deadline_exceeded",
            "outcome": "indeterminate",
            "message": "effect may have occurred; do not blindly retry",
        }
        status = 1
    except CLIOutputLimit:
        event = {
            "error": "output_limit",
            "outcome": "indeterminate",
            "message": "output cutoff reached; some received data could not be emitted",
        }
        status = 1
    except RelayError as error:
        uncertain = error.code in {"closed", "connection_failed", "invalid_receipt"}
        event = {"error": error.code, "outcome": "indeterminate" if uncertain else "no_effect"}
        status = 1
    except KeyboardInterrupt:
        event = {"error": "cancelled", "outcome": "indeterminate"}
        status = 130
    except (ValueError, TypeError):
        event = {
            "error": "invalid_configuration_or_input",
            "outcome": "no_effect",
            "message": "check v2 config, explicit administrator credential and command arguments",
        }
        status = 2
    except OSError:
        event = {"error": "io_failed", "outcome": "indeterminate"}
        status = 1
    try:
        _timed_write(
            sys.stderr, json.dumps(event, separators=(",", ":")) + "\n", time.monotonic() + 0.2
        )
    except (OSError, ValueError):
        pass
    raise SystemExit(status)


async def _client_run(
    operation: str,
    *,
    name: str,
    endpoint: str,
    network: str,
    credential: str | None,
    destination: str | None,
    payload: bytes,
    deadline: float,
    count: int,
    max_unrelated: int,
    max_output_bytes: int,
    incoming: _Incoming | None,
) -> None:
    remaining = _positive_deadline(deadline - time.monotonic())
    output = _OutputBudget(
        max_count=count if operation == "receive" else max_unrelated,
        max_bytes=max_output_bytes,
        deadline=deadline,
    )
    node = None
    failed = False
    try:
        async with asyncio.timeout(remaining):
            node = await Node.connect(name, endpoint, timeout=remaining)
            result = await _peer_operation(
                node,
                operation,
                destination=destination,
                payload=payload,
                network=network,
                credential=credential,
                timeout=remaining,
                count=count,
                output=output,
                incoming=incoming,
                ready=lambda: _status(
                    {"event": "ready", "name": name, "network": network}, deadline
                ),
            )
            _status(result, deadline)
    except BaseException:
        failed = True
        raise
    finally:
        if node is not None:
            try:
                await node.close(timeout=0.2)
            except (RelayError, ReceiptTimeout) as error:
                if not failed:
                    code = error.code if isinstance(error, RelayError) else "release_timeout"
                    raise CLIReleaseError(code) from None


def _client(
    operation: str,
    *,
    name: str,
    endpoint: str,
    network: str,
    join_token_env: str | None,
    destination: str | None = None,
    input_file: Path | None = None,
    request_file: Path | None = None,
    timeout: float = 5,
    max_bytes: int = 1048576,
    count: int = 1,
    max_unrelated: int = 64,
    max_output_bytes: int = 1048576,
) -> None:
    def invoke():
        deadline = time.monotonic() + _positive_deadline(timeout)
        selected = network
        if not valid_name(name) or not valid_name(selected):
            raise CLIInputError("invalid client name or network")
        credential = _env_token(join_token_env)
        payload = (
            b""
            if operation == "receive"
            else _read_payload(input_file, max_bytes, deadline=deadline)
        )
        incoming = None
        if operation == "reply":
            if request_file is None:
                raise CLIInputError("incoming request metadata file required")
            incoming = _decode_incoming(
                _read_payload(
                    request_file, min(16 * 1024 * 1024, max_bytes * 2 + 4096), deadline=deadline
                ),
                max_bytes,
            )
            selected = incoming.network
        asyncio.run(
            _client_run(
                operation,
                name=name,
                endpoint=endpoint,
                network=selected,
                credential=credential,
                destination=destination,
                payload=payload,
                deadline=deadline,
                count=count,
                max_unrelated=max_unrelated,
                max_output_bytes=max_output_bytes,
                incoming=incoming,
            )
        )

    _execute(invoke)


def main(*, config: Path | None = None) -> None:
    """Start the relay; prints the bound endpoint after native bind succeeds.

    Parameters
    ----------
    config
        Strict v2 TOML; administrative changes save to this SAME file. Without
        a file, configuration is memory-only. Endpoints and native limits are
        startup-only. NODALWIRE_ADMIN_TOKEN overrides configured verifier;
        missing or malformed administrator credentials fail before bind.
    """

    def start():
        settings = load_config(config) if config is not None else RelayConfig()
        asyncio.run(_serve(ConfigStore(settings, config)))

    _execute(start)


app.command(main, name="serve")


@app.command
def send(
    destination: str,
    *,
    name: str,
    endpoint: str = "tcp://127.0.0.1:5555",
    network: str = "default",
    join_token_env: str | None = None,
    input_file: Path | None = None,
    timeout: float = 5,
    max_bytes: int = 1048576,
) -> None:
    """Send bounded stdin/file bytes once, then disconnect; no retry.

    A successful receipt is native queue acceptance, not application execution.
    --join-token-env names an environment variable, never the credential itself.
    --timeout includes input reading, connection and operation (cleanup <=0.2s).
    Omitted --network selects default ONLY. Each invocation explicitly joins anew.
    """
    _client(
        "send",
        destination=destination,
        name=name,
        endpoint=endpoint,
        network=network,
        join_token_env=join_token_env,
        input_file=input_file,
        timeout=timeout,
        max_bytes=max_bytes,
    )


@app.command
def receive(
    *,
    name: str,
    endpoint: str = "tcp://127.0.0.1:5555",
    network: str = "default",
    join_token_env: str | None = None,
    timeout: float = 5,
    count: int = 1,
    max_output_bytes: int = 2097152,
) -> None:
    """Receive a finite count of messages as base64 JSON, then disconnect.

    Emits ready after JOIN, then message events and a completion event. There is
    no continuous mode or connection/membership shared with later invocations.
    --max-output-bytes bounds message JSON; ready/completion are small fixed status.
    """
    _client(
        "receive",
        name=name,
        endpoint=endpoint,
        network=network,
        join_token_env=join_token_env,
        timeout=timeout,
        count=count,
        max_output_bytes=max_output_bytes,
    )


@app.command
def request(
    destination: str,
    *,
    name: str,
    endpoint: str = "tcp://127.0.0.1:5555",
    network: str = "default",
    join_token_env: str | None = None,
    input_file: Path | None = None,
    timeout: float = 5,
    max_bytes: int = 1048576,
    max_unrelated: int = 64,
    max_output_bytes: int = 1048576,
) -> None:
    """Hold one connection for a correlated reply, then disconnect.

    Emits unrelated ordinary messages (base64 JSON), never silently discards them.
    Count/byte cutoff cancels the wait with an uncertain outcome; timeout does NOT
    mean the remote application did nothing. No retry/reconnect/replay.
    --max-output-bytes bounds unrelated events; terminal reply JSON <=2MiB.
    Matching is sender/network/kind/unpredictable ID, NOT authenticated identity.
    """
    _client(
        "request",
        destination=destination,
        name=name,
        endpoint=endpoint,
        network=network,
        join_token_env=join_token_env,
        input_file=input_file,
        timeout=timeout,
        max_bytes=max_bytes,
        max_unrelated=max_unrelated,
        max_output_bytes=max_output_bytes,
    )


@app.command
def reply(
    *,
    name: str,
    request_file: Path,
    endpoint: str = "tcp://127.0.0.1:5555",
    join_token_env: str | None = None,
    input_file: Path | None = None,
    timeout: float = 5,
    max_bytes: int = 1048576,
) -> None:
    """Reply using a prior receive message JSON file and new stdin/file bytes.

    The file must contain exactly one message event with the original request
    envelope. Uses its incoming network explicitly and joins on a NEW connection;
    no hidden connection is retained. The requester must still be connected.
    """
    _client(
        "reply",
        name=name,
        endpoint=endpoint,
        network="default",
        request_file=request_file,
        join_token_env=join_token_env,
        input_file=input_file,
        timeout=timeout,
        max_bytes=max_bytes,
    )


async def _admin_run(operation, arguments, expected_revision, endpoint, token, deadline):
    client = None
    try:
        async with asyncio.timeout(_positive_deadline(deadline - time.monotonic())):
            client = await AdminClient.connect(
                endpoint, token=token, timeout=deadline - time.monotonic()
            )
            receipt = await client.call(operation, arguments, expected_revision=expected_revision)
            _status(
                {"event": "admin", "revision": receipt.revision, "result": receipt.result}, deadline
            )
    finally:
        if client is not None:
            await client.close()


@app.command
def admin(
    operation: str,
    *,
    endpoint: str = "tcp://127.0.0.1:5556",
    token_env: str = "NODALWIRE_ADMIN_TOKEN",
    network: str | None = None,
    member: str | None = None,
    protected: bool | None = None,
    credential_env: str | None = None,
    expected_revision: int | None = None,
    timeout: float = 5,
) -> None:
    """One administrative operation on the SEPARATE loopback endpoint.

    Operations: config.get, network.list/get/create/update/rotate/delete,
    member.list/remove, admin.rotate (use their dotted names). Mutation requires
    --expected-revision from a prior explicit read; no automatic retry/read-modify
    replay. --protected/--no-protected is explicit for network.update.
    --token-env selects administrator credential; --credential-env selects NEW
    network/admin credential. Both flags name variables, never bearer values.
    Env-managed server admin rotation is rejected. Reads redact all verifiers.
    """

    def invoke():
        deadline = time.monotonic() + _positive_deadline(timeout)
        token = _env_token(token_env, required=True)
        credential = _env_token(credential_env)
        arguments = _admin_arguments(
            operation, network=network, member=member, protected=protected, credential=credential
        )
        _admin_revision(operation, expected_revision)
        asyncio.run(_admin_run(operation, arguments, expected_revision, endpoint, token, deadline))

    _execute(invoke)
