"""Async DEALER node: bounded inbox/control/app waiters and no retry or replay."""

import asyncio
import json
import math
import re
import secrets
from dataclasses import dataclass

import zmq
import zmq.asyncio

from ...config import local_endpoint
from ...protocol import (
    CLOSE,
    DATA,
    DEFAULT_NETWORK,
    ERROR,
    HEARTBEAT,
    HELLO,
    JOIN,
    LEAVE,
    OK,
    SEND,
    VERSION,
    ReceiptTimeout,
    RelayError,
    valid_credential,
    valid_name,
)
from .envelope import Envelope, decode_envelope, encode_envelope

_TOKEN = re.compile(rb"[0-9a-f]{32}\Z")
_DECIMAL = re.compile(rb"[1-9][0-9]*\Z")
_LEASE = re.compile(rb"(?:0|[1-9][0-9]*)(?:\.[0-9]+)?\Z")
_RELAY_ERRORS = frozenset({
    "invalid_name", "admission_denied", "duplicate_name", "not_registered",
    "invalid_command", "invalid_destination", "invalid_network", "network_not_found",
    "join_denied", "not_member", "destination_not_member", "payload_too_large",
    "route_denied", "destination_unavailable", "destination_full", "unsupported_version",
})


def _seconds(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be finite and positive")
    return value


def _ascii(frame: bytes) -> str | None:
    try:
        return frame.decode("ascii")
    except UnicodeError:
        return None


@dataclass(frozen=True)
class Message:
    sender: str
    payload: bytes
    network: str = DEFAULT_NETWORK


@dataclass(frozen=True)
class MembershipReceipt:
    network: str
    joined: bool
    changed: bool


@dataclass
class _Pending:
    token: bytes
    command: bytes
    network: bytes | None
    future: asyncio.Future[tuple[bytes, ...]]
    app_identity: str | None = None


@dataclass
class _AppWaiter:
    sender: str
    network: str
    future: asyncio.Future[Message]


class Node:
    """One registration; names are ephemeral routing labels, not identities.

    Control receipts and application request waiters each have max_pending capacity.
    Full ordinary inbox pauses the sole native reader, including control/reply
    progress. Drain receive() concurrently. Queue acceptance isn't remote execution.
    """

    def __init__(
        self, name: str, endpoint: str, *, timeout: float = 5.0,
        send_hwm: int = 64, receive_hwm: int = 64, inbox_size: int = 64,
        max_pending: int = 128,
    ) -> None:
        if not valid_name(name):
            raise ValueError("invalid logical node name")
        _seconds(timeout)
        for value in (send_hwm, receive_hwm, inbox_size, max_pending):
            if type(value) is not int or not 0 < value <= 2**31 - 1:
                raise ValueError("queue limits must be positive native integers")
        endpoint = local_endpoint(endpoint)
        self.name = name
        self.endpoint = endpoint
        self.timeout = timeout
        self.max_pending = max_pending
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.IPV6, int(endpoint.startswith("tcp://[")))
        self.socket.setsockopt(zmq.IDENTITY, secrets.token_bytes(16))
        self.socket.setsockopt(zmq.IMMEDIATE, 1)
        self.socket.setsockopt(zmq.SNDHWM, send_hwm)
        self.socket.setsockopt(zmq.RCVHWM, receive_hwm)
        # MAXMSGSIZE may apply only to subsequent connections. Set a native
        # protocol ceiling now; enforce the negotiated smaller limit in the reader.
        self.socket.setsockopt(zmq.MAXMSGSIZE, 2**31 - 1)
        self._inbox: asyncio.Queue[Message] = asyncio.Queue(maxsize=inbox_size)
        self._pending: dict[bytes, _Pending] = {}
        self._app_pending: dict[str, _AppWaiter] = {}
        self._receiver: asyncio.Task[None] | None = None
        self._heartbeat: asyncio.Task[None] | None = None
        self._token: bytes | None = None
        self._max_payload = 0
        self._closed = asyncio.Event()
        self._cleanup_done = asyncio.Event()
        self._cleanup_task: asyncio.Task[None] | None = None
        self._closing = False
        try:
            self.socket.connect(endpoint)
        except BaseException:
            self.socket.close(linger=0)
            self.context.term()
            raise

    @classmethod
    async def connect(cls, name: str, endpoint: str = "tcp://127.0.0.1:5555", **options) -> "Node":
        """Await registration, even with zero memberships. No reconnect/replay."""
        node = cls(name, endpoint, **options)
        node._receiver = asyncio.create_task(node._read(), name=f"relay-inbox-{name}")
        try:
            _, lease, _, _ = await node._request(HELLO, name.encode("ascii"), initial=True)
            node._heartbeat = asyncio.create_task(
                node._beat(float(lease) / 3), name=f"relay-heartbeat-{name}"
            )
            return node
        except BaseException:
            await node._cleanup()
            raise

    async def _request(
        self, command: bytes, *frames: bytes, initial: bool = False,
        timeout: float | None = None, app_identity: str | None = None,
    ) -> tuple[bytes, ...]:
        seconds = _seconds(self.timeout if timeout is None else timeout)
        if self._closed.is_set():
            error = RelayError("closed")
            self._app_error(app_identity, error)
            raise error
        if len(self._pending) >= self.max_pending:
            error = RelayError("pending_full")
            self._app_error(app_identity, error)
            raise error
        request = secrets.token_hex(16).encode("ascii")
        token = b"" if initial else self._token
        assert token is not None
        future = asyncio.get_running_loop().create_future()
        self._pending[request] = _Pending(
            token, command, frames[0] if command in (JOIN, LEAVE) else None, future, app_identity
        )
        body = [VERSION, command]
        if not initial:
            body.append(token)
        body.extend([request, *frames])
        try:
            async with asyncio.timeout(seconds):
                try:
                    await self.socket.send_multipart(body, flags=0 if initial else zmq.DONTWAIT)
                except zmq.Again as exc:
                    raise RelayError("local_queue_full") from exc
                except zmq.ZMQError as exc:
                    raise RelayError("connection_failed") from exc
                return await future
        except TimeoutError as exc:
            error = ReceiptTimeout("routing receipt timed out; effect uncertain")
            self._app_error(app_identity, error)
            raise error from exc
        except BaseException as exc:
            self._app_error(app_identity, exc)
            raise
        finally:
            self._pending.pop(request, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()

    def _success(self, pending: _Pending, extra: tuple[bytes, ...]) -> bool:
        if pending.command == HELLO:
            if len(extra) != 4:
                return False
            token, lease, limit, memberships = extra
            try:
                valid = (
                    _TOKEN.fullmatch(token) is not None
                    and len(lease) <= 32
                    and _LEASE.fullmatch(lease) is not None
                    and 0.1 <= float(lease) <= 3600
                    and _DECIMAL.fullmatch(limit) is not None
                    and len(limit) <= 10
                    and int(limit) <= 2**31 - 4096
                    and len(memberships) <= 32
                    and json.loads(memberships.decode("ascii")) in ([], [DEFAULT_NETWORK])
                )
            except (ValueError, UnicodeError, OverflowError):
                return False
            if not valid:
                return False
            self._token = token
            self._max_payload = int(limit)
            self.socket.setsockopt(zmq.MAXMSGSIZE, self._max_payload + 4096)
            return True
        if pending.command in (JOIN, LEAVE):
            return len(extra) == 2 and extra[0] == pending.network and extra[1] in (b"0", b"1")
        return pending.command in (SEND, CLOSE) and not extra

    async def _read(self) -> None:
        try:
            while True:
                frames = await self.socket.recv_multipart()
                if len(frames) < 4 or frames[0] != VERSION:
                    continue
                command, token = frames[1:3]
                if command == DATA:
                    if len(frames) != 6 or token != self._token:
                        continue
                    network, sender = _ascii(frames[3]), _ascii(frames[4])
                    if (not valid_name(network) or not valid_name(sender)
                            or len(frames[5]) > self._max_payload):
                        continue
                    message = Message(sender, frames[5], network)
                    envelope = decode_envelope(message.payload, max_bytes=self._max_payload)
                    waiter = self._app_pending.get(envelope.id) if envelope is not None else None
                    if (waiter is not None and envelope.kind == "reply"
                            and waiter.sender == sender and waiter.network == network):
                        # Ownership is decided in the sole reader before any continuation.
                        del self._app_pending[envelope.id]
                        waiter.future.set_result(Message(sender, envelope.payload, network))
                    else:
                        await self._inbox.put(message)
                    continue
                pending = self._pending.get(frames[3])
                if pending is None or pending.token != token or pending.future.done():
                    continue
                if command == OK and self._success(pending, tuple(frames[4:])):
                    pending.future.set_result(tuple(frames[4:]))
                elif command == ERROR and len(frames) == 5 and _ascii(frames[4]) in _RELAY_ERRORS:
                    error = RelayError(frames[4].decode("ascii"))
                    self._app_error(pending.app_identity, error)
                    pending.future.set_exception(error)
                else:
                    error = RelayError("invalid_receipt")
                    self._app_error(pending.app_identity, error)
                    pending.future.set_exception(error)
        except asyncio.CancelledError:
            raise
        except Exception:
            self._closed.set()
            self._fail_pending("connection_failed")

    def _app_error(self, identity: str | None, error: BaseException) -> None:
        # The reader/local operation decides terminal ownership synchronously,
        # never via a later send-task done callback that DATA could overtake.
        waiter = self._app_pending.pop(identity, None)
        if waiter is not None:
            waiter.future.set_exception(error)

    @staticmethod
    async def _join_owned(*tasks: asyncio.Task) -> None:
        """Join operation-owned children without a cleanup cancel losing its result.

        Call only after the operation already has a terminal result/error/cancel.
        The original terminal event remains authoritative through repeated caller
        cancellation while joining. No shared reader/writer is cancelled here.
        """
        for task in tasks:
            task.cancel()
        joining = asyncio.gather(*tasks, return_exceptions=True)
        while True:
            try:
                await asyncio.shield(joining)
                return
            except asyncio.CancelledError:
                pass

    def _fail_pending(self, code: str) -> None:
        for pending in self._pending.values():
            if not pending.future.done():
                pending.future.set_exception(RelayError(code))
        waiters = tuple(self._app_pending.values())
        self._app_pending.clear()
        for waiter in waiters:
            if not waiter.future.done():
                waiter.future.set_exception(RelayError(code))

    async def _beat(self, interval: float) -> None:
        assert self._token is not None
        while True:
            await asyncio.sleep(interval)
            try:
                await self.socket.send_multipart(
                    [VERSION, HEARTBEAT, self._token], flags=zmq.DONTWAIT
                )
            except zmq.Again:
                pass  # No heartbeat backlog; local congestion may expire the lease.

    def _active(self) -> None:
        if self._closing or self._closed.is_set():
            raise RelayError("closed")

    async def join(
        self, network: str, credential: str | None = None, *, timeout: float | None = None,
    ) -> MembershipReceipt:
        self._active()
        if not valid_name(network):
            raise ValueError("invalid network name")
        if credential is not None and not valid_credential(credential):
            raise ValueError("invalid join credential")
        _, changed = await self._request(
            JOIN, network.encode("ascii"),
            b"" if credential is None else credential.encode("ascii"), timeout=timeout,
        )
        return MembershipReceipt(network, True, changed == b"1")

    async def leave(self, network: str, *, timeout: float | None = None) -> MembershipReceipt:
        self._active()
        if not valid_name(network):
            raise ValueError("invalid network name")
        _, changed = await self._request(LEAVE, network.encode("ascii"), timeout=timeout)
        return MembershipReceipt(network, False, changed == b"1")

    async def send(
        self, destination: str, payload: bytes, *, network: str = DEFAULT_NETWORK,
        timeout: float | None = None,
    ) -> None:
        """Native target queue acceptance only. Timeout/cancel may occur after effect."""
        self._active()
        if not valid_name(destination):
            raise ValueError("invalid destination name")
        if not valid_name(network):
            raise ValueError("invalid network name")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if len(payload) > self._max_payload:
            raise RelayError("payload_too_large")
        await self._request(
            SEND, network.encode("ascii"), destination.encode("ascii"), payload, timeout=timeout
        )

    def receive_nowait(self) -> Message | None:
        """Pop one queued ordinary message; never read native data or app replies."""
        try:
            return self._inbox.get_nowait()
        except asyncio.QueueEmpty:
            return None

    async def receive(self) -> Message:
        """Single bounded ordinary inbox; queued data remains readable after close."""
        if not self._inbox.empty():
            return self._inbox.get_nowait()
        if self._closed.is_set():
            raise RelayError("closed")
        message = asyncio.create_task(self._inbox.get())
        closed = asyncio.create_task(self._closed.wait())
        try:
            await asyncio.wait([message, closed], return_when=asyncio.FIRST_COMPLETED)
            if message.done():
                return message.result()
            raise RelayError("closed")
        except asyncio.CancelledError:
            # Do not lose ordinary DATA already claimed by this waiter. An inbox
            # delivery that completed first wins a subsequent cancellation.
            if message.done() and not message.cancelled():
                return message.result()
            raise
        finally:
            await self._join_owned(message, closed)

    async def request(
        self, destination: str, payload: bytes, *, network: str = DEFAULT_NETWORK,
        timeout: float | None = None,
    ) -> Message:
        """First terminal event wins: matching reply, send failure, cancel or deadline.

        A matching reply can succeed without a routing receipt. Unrelated/late data
        stays in receive(); correlation by ephemeral names is not authentication.
        """
        self._active()
        seconds = _seconds(self.timeout if timeout is None else timeout)
        if not valid_name(destination) or not valid_name(network):
            raise ValueError("invalid destination or network name")
        if len(self._app_pending) >= self.max_pending:
            raise RelayError("pending_full")
        identity = secrets.token_hex(16)
        encoded = encode_envelope(
            Envelope("request", identity, payload), max_bytes=self._max_payload
        )
        loop = asyncio.get_running_loop()
        future = loop.create_future()
        waiter = _AppWaiter(destination, network, future)
        self._app_pending[identity] = waiter

        def fail(error: BaseException) -> None:
            if self._app_pending.get(identity) is waiter:
                del self._app_pending[identity]
                future.set_exception(error)

        timer = loop.call_later(
            seconds, fail, ReceiptTimeout("application reply timed out; effect uncertain")
        )
        sender = asyncio.create_task(self._request(
            SEND, network.encode("ascii"), destination.encode("ascii"), encoded,
            timeout=seconds, app_identity=identity,
        ))

        def sent(task: asyncio.Task) -> None:
            if task.cancelled():
                return
            if (error := task.exception()) is not None:
                fail(error)

        sender.add_done_callback(sent)
        try:
            return await asyncio.shield(future)
        except asyncio.CancelledError:
            # A reader-completed result already owns the message; don't lose it to
            # cancellation between set_result and this coroutine's resumption.
            if future.done():
                return future.result()
            if self._app_pending.get(identity) is waiter:
                del self._app_pending[identity]
            future.cancel()
            raise
        finally:
            timer.cancel()
            self._app_pending.pop(identity, None)
            await self._join_owned(sender)
            if future.done() and not future.cancelled():
                future.exception()

    async def reply(
        self, incoming: Message, payload: bytes, *, timeout: float | None = None,
    ) -> None:
        """Reply on incoming.network, with the request ID copied before first await."""
        self._active()
        if not isinstance(incoming, Message):
            raise TypeError("expected incoming Message")
        envelope = decode_envelope(incoming.payload, max_bytes=self._max_payload)
        if envelope is None or envelope.kind != "request":
            raise ValueError("incoming message is not a request")
        encoded = encode_envelope(
            Envelope("reply", envelope.id, payload), max_bytes=self._max_payload
        )
        await self.send(incoming.sender, encoded, network=incoming.network, timeout=timeout)

    async def _cleanup(self) -> None:
        if self._cleanup_task is None:
            self._cleanup_task = asyncio.create_task(
                self._dispose(), name=f"relay-close-{self.name}"
            )
        cancelled = False
        while True:
            try:
                await asyncio.shield(self._cleanup_task)
                break
            except asyncio.CancelledError:
                cancelled = True
        if cancelled:
            raise asyncio.CancelledError

    async def _dispose(self) -> None:
        self._closed.set()
        self._fail_pending("closed")
        for task in (self._heartbeat, self._receiver):
            if task is not None:
                task.cancel()
        try:
            await asyncio.gather(
                *(task for task in (self._heartbeat, self._receiver) if task is not None),
                return_exceptions=True,
            )
        finally:
            self.socket.close(linger=0)
            self.context.term()
            self._cleanup_done.set()

    async def close(self, *, timeout: float | None = None) -> None:
        """Attempt release, always clean up; failed receipt remains uncertain."""
        if self._closing:
            await self._cleanup_done.wait()
            return
        self._closing = True
        try:
            if self._token is not None and not self._closed.is_set():
                await self._request(CLOSE, timeout=timeout)
        finally:
            await self._cleanup()

    async def __aenter__(self) -> "Node":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
