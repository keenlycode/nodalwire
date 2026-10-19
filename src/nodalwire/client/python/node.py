"""Async DEALER node with one bounded inbox and transport-owned receipt correlation."""

import asyncio
import secrets
from dataclasses import dataclass

import zmq
import zmq.asyncio

from ...config import local_endpoint
from ...protocol import (
    CLOSE,
    DATA,
    ERROR,
    HEARTBEAT,
    HELLO,
    OK,
    SEND,
    VERSION,
    ReceiptTimeout,
    RelayError,
    valid_name,
)


@dataclass(frozen=True)
class Message:
    sender: str
    payload: bytes


class Node:
    """Connect by logical name; send bytes, receive sender+bytes, and close.

    Native queues, inbox and outstanding requests are bounded. When the inbox is
    full, reading pauses (including receipts); drain it concurrently with sending.
    Socket queue acceptance is not application delivery or execution.
    """

    def __init__(
        self,
        name: str,
        endpoint: str,
        *,
        timeout: float = 5.0,
        send_hwm: int = 64,
        receive_hwm: int = 64,
        inbox_size: int = 64,
        max_pending: int = 128,
    ) -> None:
        if not valid_name(name):
            raise ValueError("invalid logical node name")
        if timeout <= 0:
            raise ValueError("timeout must be positive")
        for value in (send_hwm, receive_hwm, inbox_size, max_pending):
            if type(value) is not int or value <= 0:
                raise ValueError("queue limits must be positive integers")
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
        self._inbox: asyncio.Queue[Message] = asyncio.Queue(maxsize=inbox_size)
        self._pending: dict[bytes, tuple[bytes, asyncio.Future[tuple[bytes, ...]]]] = {}
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
        """Await admission; failure closes owned resources. No reconnect or replay."""
        node = cls(name, endpoint, **options)
        node._receiver = asyncio.create_task(node._read(), name=f"relay-inbox-{name}")
        try:
            token, lease, payload_limit = await node._request(
                HELLO, name.encode("ascii"), initial=True
            )
            node._token = token
            node._max_payload = int(payload_limit)
            node.socket.setsockopt(zmq.MAXMSGSIZE, node._max_payload + 4096)
            node._heartbeat = asyncio.create_task(
                node._beat(float(lease) / 3), name=f"relay-heartbeat-{name}"
            )
            return node
        except BaseException:
            await node._cleanup()
            raise

    async def _request(
        self,
        command: bytes,
        *frames: bytes,
        initial: bool = False,
        timeout: float | None = None,
    ) -> tuple[bytes, ...]:
        if self._closed.is_set():
            raise RelayError("closed")
        if len(self._pending) >= self.max_pending:
            raise RelayError("pending_full")
        request = secrets.token_hex(16).encode("ascii")
        token = b"" if initial else self._token
        assert token is not None
        future = asyncio.get_running_loop().create_future()
        self._pending[request] = (token, future)
        body = [VERSION, command]
        if not initial:
            body.append(token)
        body.extend([request, *frames])
        try:
            async with asyncio.timeout(self.timeout if timeout is None else timeout):
                try:
                    await self.socket.send_multipart(body, flags=0 if initial else zmq.DONTWAIT)
                except zmq.Again as exc:
                    raise RelayError("local_queue_full") from exc
                return await future
        except TimeoutError as exc:
            raise ReceiptTimeout("routing receipt timed out; effect uncertain") from exc
        finally:
            self._pending.pop(request, None)
            if not future.done():
                future.cancel()
            elif not future.cancelled():
                future.exception()  # Consume a concurrent close/receiver failure.

    async def _read(self) -> None:
        try:
            while True:
                frames = await self.socket.recv_multipart()
                if len(frames) < 4 or frames[0] != VERSION:
                    continue
                command, token = frames[1:3]
                if command == DATA and len(frames) == 5 and token == self._token:
                    sender = frames[3].decode("ascii")
                    if valid_name(sender) and len(frames[4]) <= self._max_payload:
                        await self._inbox.put(Message(sender, frames[4]))
                    continue
                request = frames[3]
                pending = self._pending.get(request)
                if pending is None or pending[0] != token or pending[1].done():
                    continue
                future = pending[1]
                if command == OK:
                    extra = tuple(frames[4:])
                    if token == b"" and len(extra) == 3:
                        # Install incarnation before any DATA already behind HELLO's reply.
                        self._token = extra[0]
                        self._max_payload = int(extra[2])
                    future.set_result(extra)
                elif command == ERROR and len(frames) == 5:
                    future.set_exception(RelayError(frames[4].decode("ascii")))
        except asyncio.CancelledError:
            raise
        except Exception:
            self._closed.set()
            self._fail_pending("connection_failed")

    def _fail_pending(self, code: str) -> None:
        for _, future in self._pending.values():
            if not future.done():
                future.set_exception(RelayError(code))

    async def _beat(self, interval: float) -> None:
        assert self._token is not None
        while True:
            await asyncio.sleep(interval)
            try:
                await self.socket.send_multipart(
                    [VERSION, HEARTBEAT, self._token], flags=zmq.DONTWAIT
                )
            except zmq.Again:
                pass  # No heartbeat backlog; lease may expire under local congestion.

    async def send(self, destination: str, payload: bytes, *, timeout: float | None = None) -> None:
        """Wait for Router queue acceptance or status (never remote execution).

        Timeout, cancellation and interrupted lifecycle have uncertain effects.
        """
        if self._closing or self._closed.is_set():
            raise RelayError("closed")
        if not valid_name(destination):
            raise ValueError("invalid destination name")
        if not isinstance(payload, bytes):
            raise TypeError("payload must be bytes")
        if len(payload) > self._max_payload:
            raise RelayError("payload_too_large")
        await self._request(SEND, destination.encode("ascii"), payload, timeout=timeout)

    async def receive(self) -> Message:
        """Read the single inbox; queued data remains readable after close."""
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
        finally:
            for task in (message, closed):
                task.cancel()
            await asyncio.gather(message, closed, return_exceptions=True)

    async def _cleanup(self) -> None:
        # Cleanup has independent ownership: cancellation of a close/connect caller
        # must not interrupt joins or leave native resources and tasks behind.
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
            # A repeated close can return only after this native cleanup boundary.
            self.socket.close(linger=0)
            self.context.term()
            self._cleanup_done.set()

    async def close(self, *, timeout: float | None = None) -> None:
        """Attempt registration release, always clean up; failed receipt stays uncertain."""
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
