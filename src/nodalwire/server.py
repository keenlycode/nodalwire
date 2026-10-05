"""One ROUTER socket: admission, lease ownership and nonblocking opaque forwarding."""

import secrets
import time
from dataclasses import dataclass

import zmq
import zmq.asyncio

from .config import RelayConfig
from .protocol import CLOSE, DATA, ERROR, HEARTBEAT, HELLO, OK, SEND, VERSION, valid_name


@dataclass
class _Registration:
    name: str
    address: bytes
    token: bytes
    expires: float


class Relay:
    """Owns a local context/socket; call start(), run(), and finally close().

    Every destination send uses ROUTER_MANDATORY and DONTWAIT. A successful receipt
    means native socket queue acceptance only. There is no Python outbound queue.
    """

    def __init__(self, config: RelayConfig | None = None) -> None:
        self.config = config or RelayConfig()
        self.context: zmq.Context | None = None
        self.socket: zmq.asyncio.Socket | None = None
        self.endpoint: str | None = None
        self._names: dict[str, _Registration] = {}
        self._addresses: dict[bytes, _Registration] = {}
        self._running = False

    async def start(self) -> str:
        if self.context is not None:
            raise RuntimeError("relay already started")
        self.context = zmq.Context()
        try:
            self.socket = zmq.asyncio.Socket(self.context, zmq.ROUTER)
            self.socket.setsockopt(zmq.LINGER, 0)
            self.socket.setsockopt(zmq.IPV6, int(self.config.endpoint.startswith("tcp://[")))
            self.socket.setsockopt(zmq.ROUTER_MANDATORY, 1)
            self.socket.setsockopt(zmq.ROUTER_HANDOVER, 0)
            self.socket.setsockopt(zmq.SNDHWM, self.config.send_hwm)
            self.socket.setsockopt(zmq.RCVHWM, self.config.receive_hwm)
            self.socket.setsockopt(zmq.MAXMSGSIZE, self.config.max_payload_bytes + 4096)
            self.socket.bind(self.config.endpoint)
            self.endpoint = self.socket.getsockopt(zmq.LAST_ENDPOINT).decode("utf-8")
            return self.endpoint
        except BaseException:
            await self.close()
            raise

    def _remove(self, registration: _Registration) -> None:
        # Fence removal by object identity even if a name/address was later reused.
        if self._names.get(registration.name) is registration:
            del self._names[registration.name]
        if self._addresses.get(registration.address) is registration:
            del self._addresses[registration.address]

    def _expire(self) -> None:
        now = time.monotonic()
        for registration in tuple(self._names.values()):
            if registration.expires <= now:
                self._remove(registration)

    async def _emit(self, address: bytes, *frames: bytes) -> str | None:
        assert self.socket is not None
        try:
            await self.socket.send_multipart([address, VERSION, *frames], flags=zmq.DONTWAIT)
        except zmq.Again:
            return "destination_full"
        except zmq.ZMQError as exc:
            if exc.errno == zmq.EHOSTUNREACH:
                return "destination_unavailable"
            raise
        return None

    async def _error(self, address: bytes, token: bytes, request: bytes, code: str) -> None:
        # If a control response cannot be queued, caller sees timeout/uncertain effect.
        await self._emit(address, ERROR, token, request, code.encode("ascii"))

    async def _hello(self, address: bytes, frames: list[bytes]) -> None:
        if len(frames) != 2 or not 1 <= len(frames[0]) <= 64:
            return
        request, encoded_name = frames
        try:
            name = encoded_name.decode("ascii")
        except UnicodeDecodeError:
            name = ""
        if not valid_name(name):
            await self._error(address, b"", request, "invalid_name")
            return
        if self.config.allowed_names is not None and name not in self.config.allowed_names:
            await self._error(address, b"", request, "admission_denied")
            return
        if name in self._names or address in self._addresses:
            await self._error(address, b"", request, "duplicate_name")
            return
        registration = _Registration(
            name,
            address,
            secrets.token_hex(16).encode("ascii"),
            time.monotonic() + self.config.lease_seconds,
        )
        self._names[name] = registration
        self._addresses[address] = registration
        error = await self._emit(
            address,
            OK,
            b"",
            request,
            registration.token,
            str(self.config.lease_seconds).encode("ascii"),
            str(self.config.max_payload_bytes).encode("ascii"),
        )
        if error is not None:
            self._remove(registration)

    async def _handle(self, packet: list[zmq.Frame]) -> None:
        if len(packet) < 3 or bytes(packet[1]) != VERSION:
            return
        address, command = bytes(packet[0]), bytes(packet[2])
        frames = [bytes(frame) for frame in packet[3:]]
        if command == HELLO:
            await self._hello(address, frames)
            return
        if not frames:
            return
        token = frames[0]
        request = frames[1] if len(frames) > 1 and 1 <= len(frames[1]) <= 64 else b""
        registration = self._addresses.get(address)
        if registration is None or registration.token != token:
            if request:
                await self._error(address, token, request, "not_registered")
            return
        registration.expires = time.monotonic() + self.config.lease_seconds
        if command == HEARTBEAT and len(frames) == 1:
            return
        if command == CLOSE and len(frames) == 2 and request:
            self._remove(registration)
            await self._emit(address, OK, token, request)
            return
        if command != SEND or len(frames) != 4 or not request:
            if request:
                await self._error(address, token, request, "invalid_command")
            return
        try:
            destination = frames[2].decode("ascii")
        except UnicodeDecodeError:
            destination = ""
        payload = frames[3]
        if not valid_name(destination):
            error = "invalid_destination"
        elif len(payload) > self.config.max_payload_bytes:
            error = "payload_too_large"
        elif not self.config.permits(registration.name, destination):
            error = "route_denied"
        elif destination not in self._names:
            error = "destination_unavailable"
        else:
            target = self._names[destination]
            error = await self._emit(
                target.address, DATA, target.token, registration.name.encode("ascii"), payload
            )
        if error is None:
            await self._emit(address, OK, token, request)
        else:
            await self._error(address, token, request, error)

    async def run(self) -> None:
        if self.socket is None or self.socket.closed:
            raise RuntimeError("start the relay before run()")
        if self._running:
            raise RuntimeError("relay is already running")
        self._running = True
        try:
            while True:
                self._expire()
                if await self.socket.poll(timeout=max(1, int(self.config.lease_seconds * 100))):
                    packet = await self.socket.recv_multipart(copy=False)
                    self._expire()  # Expiry before handling, not after an old heartbeat.
                    await self._handle(packet)
        finally:
            self._running = False

    async def close(self) -> None:
        """Stop run() before closing; no persistent service or native resources remain."""
        if self._running:
            raise RuntimeError("cancel and await run() before closing the relay")
        if self.socket is not None:
            self.socket.close(linger=0)
        if self.context is not None:
            self.context.term()
        self._names.clear()
        self._addresses.clear()

    async def __aenter__(self) -> "Relay":
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
