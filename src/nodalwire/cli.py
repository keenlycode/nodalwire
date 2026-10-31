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
    help="""\
Exchange bytes between local applications through a loopback relay.

Start with serve, then receive in one terminal and send in another. Use
request/reply when an application response is needed, or admin to inspect
and manage the relay.

Quick start (POSIX shell; three terminals)
----------------------------------------
Terminal 1: start the relay. No config file is needed; an admin token is required::

    ADMIN_TOKEN=$(python -c 'import secrets; print(secrets.token_hex(32))')
    export NODALWIRE_ADMIN_TOKEN="$ADMIN_TOKEN"
    nodalwire serve

Terminal 2: wait for one message. Wait for the ready event before sending::

    nodalwire receive --name bob --timeout 30

Terminal 3: send bytes to that connected receiver::

    printf 'hello' | nodalwire send bob --name alice

The defaults are tcp://127.0.0.1:5555 for messages and
tcp://127.0.0.1:5556 for administration. Message clients use the open default network.
Stop the relay with Ctrl-C. Keep the generated credential private; admin clients
need the same value, but ordinary clients on an open network do not.

Each client command connects, joins, performs one bounded operation, then
disconnects. Later commands do not share its connection or membership. Use the
Python/Node libraries for persistent applications. Send success means queue
acceptance, not processing or durable storage. No command automatically retries.
Credentials grant permission, not authenticated peer-name identity.

Run nodalwire COMMAND --help for options and examples for that command.
""",
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
        "id": message.id,
        "reply_to": message.reply_to,
        "network": message.network,
        "sender": message.sender,
        "payload": base64.b64encode(message.payload).decode("ascii"),
    }


def _valid_message_id(value) -> bool:
    return (
        isinstance(value, str)
        and len(value) == 32
        and all(char in "0123456789abcdef" for char in value)
    )


def _decode_incoming(data: bytes, max_payload: int) -> Message:
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate input key")
            result[key] = value
        return result

    def reject_constant(_value):
        raise ValueError("nonfinite JSON number")

    try:
        item = json.loads(data, object_pairs_hook=unique, parse_constant=reject_constant)
        if not isinstance(item, dict) or set(item) != {
            "event", "id", "reply_to", "network", "sender", "payload"
        }:
            raise ValueError("invalid message fields")
        if (
            item["event"] != "message"
            or not _valid_message_id(item["id"])
            or (item["reply_to"] is not None and not _valid_message_id(item["reply_to"]))
            or not all(valid_name(item[key]) for key in ("network", "sender"))
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
    return Message(
        id=item["id"],
        sender=item["sender"],
        network=item["network"],
        payload=payload,
        reply_to=item["reply_to"],
    )


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
    incoming: Message | None = None,
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
            raise CLIInputError("incoming message metadata required")
        network = incoming.network
    async with asyncio.timeout(_positive_deadline(timeout)):
        # Even open nondefault networks require a new explicit join per invocation.
        await node.join(network, credential, timeout=timeout)
        if operation == "send":
            message_id = await node.send(destination, payload, network=network, timeout=timeout)
            return {
                "event": "accepted",
                "id": message_id,
                "reply_to": None,
                "network": network,
                "recipient": destination,
                "meaning": "native_queue_acceptance_only",
            }
        if operation == "reply":
            message_id = await node.reply(incoming, payload, timeout=timeout)
            return {
                "event": "accepted",
                "id": message_id,
                "reply_to": incoming.id,
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
    incoming: Message | None,
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
    """Start a foreground relay for local applications; stop with Ctrl-C.

    No config file is required. By default, messages use tcp://127.0.0.1:5555,
    administration uses tcp://127.0.0.1:5556, and clients join the open default
    network. Both endpoints are loopback-only.

    An administrator credential IS required, even without a file. Generate one
    and start the relay in a POSIX shell::

        ADMIN_TOKEN=$(python -c 'import secrets; print(secrets.token_hex(32))')
        export NODALWIRE_ADMIN_TOKEN="$ADMIN_TOKEN"
        nodalwire serve

    Keep that value private. Admin clients need the same token. The environment
    value overrides a configured admin_verifier; missing or malformed credentials
    fail before bind. Tokens must be 1-1024 printable ASCII characters without
    spaces; use a strong random value, not an example password.

    To customize ports, create relay.toml (still using the environment token)::

        config_version = 2
        endpoint = "tcp://127.0.0.1:6000"
        admin_endpoint = "tcp://127.0.0.1:6001"

    Then run nodalwire serve --config relay.toml. Clients must select the matching
    --endpoint. If startup fails, check the credential, v2 TOML syntax and whether
    another process already owns either port. The bound message endpoint is
    printed on stdout, followed by a serving JSON status event. Failures are
    JSON on stderr.

    Parameters
    ----------
    config
        Optional existing v2 TOML file. Without it, settings and administrative
        changes are memory-only and lost on shutdown; no file is created.
        With it, administrative changes save to this same file. Endpoints and
        native limits are startup-only; use an admin_verifier or the environment
        credential described above.
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
    """Send bytes to a connected receiver, then disconnect.

    Start the relay and a receiver first (see nodalwire --help). For example::

        printf 'hello' | nodalwire send bob --name alice
        nodalwire send bob --name alice --input-file message.bin

    Success emits an accepted JSON event: the relay queued the bytes, not proof
    that Bob received or processed them or that they are durably stored. There is
    no automatic retry. Each invocation connects and joins the selected network
    anew; omitting --network selects default only.

    Parameters
    ----------
    destination
        Connected recipient's node name, for example bob; not an endpoint URL.
    name
        Sender's node name for this invocation; distinct from the recipient.
    endpoint
        Relay message endpoint (not the separate administration endpoint).
    network
        Network to join before sending. The recipient must be a member too.
    join_token_env
        Name of an environment variable containing the selected protected
        network's join token, never the token itself. Omit for an open network.
    input_file
        Read raw payload bytes from this file instead of stdin. Without it,
        pipe input or finish interactive stdin with EOF; do not pass base64.
    timeout
        Total seconds for input, connection, join and send; cleanup adds at most
        0.2 seconds. A timeout is not proof that nothing was queued.
    max_bytes
        Maximum raw payload bytes to read; oversized input is rejected.
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
    """Wait for messages, print base64 JSON events, then disconnect.

    Run this before sending to bob from another terminal::

        nodalwire receive --name bob --timeout 30
        nodalwire receive --name bob --count 3 --timeout 60

    Wait for the ready event before sending. Stdout contains one JSON event per
    line: ready after joining, message events, then completion. The payload field
    is base64, not decoded text. This is a finite receiver, not a background
    service; later commands do not inherit its connection or membership.

    Parameters
    ----------
    name
        Receiver's node name. Senders address messages to this name.
    endpoint
        Relay message endpoint (not the administration endpoint).
    network
        Network to join for this invocation; default does not join other networks.
    join_token_env
        Environment variable NAME holding this protected network's join token.
        Omit for an open network; never pass the token as a command argument.
    timeout
        Total seconds for connection, join and receiving all requested messages;
        not a separate timeout per message. Cleanup adds at most 0.2 seconds.
    count
        Number of messages to receive before successful completion; positive only.
    max_output_bytes
        Total message-event JSON byte budget. Small ready/completion status events
        are separate. Reaching a limit is not successful completion.
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
    """Send a request and wait on the same connection for an application reply.

    Bob must already be connected and able to reply. For example::

        printf 'status?' | nodalwire request bob --name alice --timeout 30

    Unlike send, this waits for a reply whose reply_to, sender and network match
    the request; these fields are not authenticated peer identity. The reply
    payload is base64 in a JSON event. Unrelated messages are emitted as ordinary
    message events, never silently discarded. A timeout or output/count cutoff
    leaves the remote outcome uncertain: the application may already have acted.
    No retry, reconnect or replay is attempted. See nodalwire reply --help for
    the responder workflow; use the SDK for a persistent request/reply service.

    Parameters
    ----------
    destination
        Connected responder's node name, not an endpoint URL.
    name
        Requester's node name; remains connected until reply or failure.
    endpoint
        Relay message endpoint (not the administration endpoint).
    network
        Network to join for this request; the responder must be a member too.
    join_token_env
        Environment variable NAME holding the protected network's join token.
        Omit for an open network; never supply the token directly.
    input_file
        Read raw request bytes from this file instead of stdin; no base64 input.
    timeout
        Total seconds for input, connection, join, send and reply wait.
        Cleanup adds at most 0.2 seconds; timeout does not undo remote work.
    max_bytes
        Maximum raw request payload bytes to read.
    max_unrelated
        Maximum unrelated message events while waiting; exceeding it cancels
        the wait with an uncertain outcome, not a successful reply.
    max_output_bytes
        Byte budget for unrelated message JSON events. The terminal reply event
        has a separate maximum of 2 MiB.
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
    """Reply to one saved incoming message using new stdin/file bytes.

    First receive a request as bob (keep Alice's request command running)::

        nodalwire receive --name bob --timeout 30 > events.jsonl

    Copy ONLY the message event line into request.json, not the ready/completion
    lines or the whole JSONL stream. Then reconnect as the same responder::

        printf 'ok' | nodalwire reply --name bob --request-file request.json

    The file must be one message JSON object with exactly event, id, reply_to,
    network, sender and payload. This command derives recipient, reply_to and
    network from it, joins on a NEW connection, sends a fresh reply, then exits.
    The requester must still be connected and waiting. For continuous responders
    prefer the Python/Node SDK; no hidden connection survives receive.

    Parameters
    ----------
    name
        Responder node name; must match the destination of the original request
        for the requester's correlation check to accept this reply.
    request_file
        JSON file containing exactly one received message event, not JSONL,
        an entire command transcript, or a reply event.
    endpoint
        Relay message endpoint that the requester is using.
    join_token_env
        Environment variable NAME holding the incoming network's join token.
        Its network is taken from request-file, not a separate --network option.
    input_file
        Read new raw reply bytes from this file instead of stdin; the saved
        request's base64 payload is not reused as the reply.
    timeout
        Total seconds for reading both files/input, connection, join and send;
        cleanup adds at most 0.2 seconds. No retry on uncertain failure.
    max_bytes
        Maximum raw reply payload bytes; also bounds accepted request metadata.
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
    """Inspect or change relay settings through its authenticated admin endpoint.

    Use the SAME administrator token as the running relay, in an environment
    variable. The default token variable is NODALWIRE_ADMIN_TOKEN. Read first::

        nodalwire admin config.get
        nodalwire admin network.list
        nodalwire admin member.list --network default

    Each success emits JSON with revision and result. For a change, pass the
    current revision from that explicit read, for example if revision is 0::

        nodalwire admin network.create --network team --expected-revision 0

    This creates an open network. For a protected network, first set a strong
    new token in TEAM_JOIN_TOKEN, then use (with the CURRENT revision)::

        nodalwire admin network.create --network team \\
            --credential-env TEAM_JOIN_TOKEN --expected-revision 0

    Operations and their additional options:

    * config.get, network.list: no additional options.
    * network.get, network.delete, member.list: --network.
    * network.create: --network, optional --credential-env (protected if supplied).
    * network.update: --network and explicit --protected or --no-protected;
      optional --credential-env for the new protection policy.
    * network.rotate: --network and --credential-env for a new join token.
    * member.remove: --network and --member.
    * admin.rotate: --credential-env for a new admin token; not allowed when the
      server's administrator credential is environment-managed.

    Every mutation also requires --expected-revision; reads must omit it. On a
    revision conflict, read and deliberately reconsider the change; no automatic
    retry/read-modify replay is performed. Reads redact credential verifiers.
    Configuration is persistent only when the relay was started with --config.

    Parameters
    ----------
    operation
        One dotted operation name listed above, for example config.get.
    endpoint
        Separate ADMIN endpoint; do not use the message endpoint on port 5555.
    token_env
        Environment variable NAME containing the CURRENT administrator token.
        Never pass the bearer value itself as an argument.
    network
        Network name required by network/member operations listed above.
    member
        Node name to remove; used only with member.remove.
    protected
        Explicit protection policy for network.update. Use --protected to
        require a join credential, or --no-protected to make the network open.
    credential_env
        Environment variable NAME containing a NEW network/admin credential.
        This is different from token-env, which authenticates the current call.
    expected_revision
        Revision from a prior read; required for mutations, forbidden for reads.
        Never reuse the example revision without checking the current value.
    timeout
        Total seconds for authentication, connection and this operation.
        Timeout is not proof a mutation failed; do not blindly retry.
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
