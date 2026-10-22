"""Serialized local relay: ephemeral membership and a separate administrative socket."""

import json
import secrets
import time
from dataclasses import dataclass, field, replace

import zmq
import zmq.asyncio

from ..admin import ADMIN_MUTATIONS, ADMIN_READS
from ..config import NetworkConfig, RelayConfig
from ..config_store import ConfigStore, ConfigStoreError, PersistenceIndeterminate
from ..credentials import make_verifier
from ..protocol import (
    ADMIN_VERSION,
    CLOSE,
    DATA,
    DEFAULT_NETWORK,
    ERROR,
    HEARTBEAT,
    HELLO,
    JOIN,
    LEAVE,
    MAX_ADMIN_JSON,
    MAX_CREDENTIAL_BYTES,
    OK,
    SEND,
    VERSION,
    json_object,
    valid_credential,
    valid_name,
)


@dataclass
class _Registration:
    name: str
    address: bytes
    token: bytes
    expires: float
    memberships: set[str] = field(default_factory=set)


class _AdminRejection(Exception):
    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


def _name(frame: bytes) -> str | None:
    if len(frame) > 128:
        return None
    try:
        value = frame.decode("ascii")
    except UnicodeError:
        return None
    return value if valid_name(value) else None


class Relay:
    """Own both loopback sockets, native queues and one serialized dispatch loop.

    No Python outbound queue. SEND success means target native queue acceptance,
    not application execution. Call start/run and cancel+await run before close.
    Configuration persistence is owned by ConfigStore, never reconstructed here.
    """

    def __init__(
        self, config: RelayConfig | None = None, *, store: ConfigStore | None = None,
    ) -> None:
        if config is not None and store is not None:
            raise ValueError("supply config or store, not both")
        # Credential resolution/validation precedes any socket/context allocation.
        self.store = store if store is not None else ConfigStore(config or RelayConfig())
        self.context: zmq.Context | None = None
        self.socket: zmq.asyncio.Socket | None = None
        self.admin_socket: zmq.asyncio.Socket | None = None
        self.endpoint: str | None = None
        self.admin_endpoint: str | None = None
        self._names: dict[str, _Registration] = {}
        self._addresses: dict[bytes, _Registration] = {}
        self._running = False

    @property
    def config(self) -> RelayConfig:
        return self.store.snapshot()

    def _socket(self, endpoint: str, max_size: int) -> zmq.asyncio.Socket:
        assert self.context is not None
        socket = zmq.asyncio.Socket(self.context, zmq.ROUTER)
        try:
            socket.setsockopt(zmq.LINGER, 0)
            socket.setsockopt(zmq.IPV6, int(endpoint.startswith("tcp://[")))
            socket.setsockopt(zmq.ROUTER_MANDATORY, 1)
            socket.setsockopt(zmq.ROUTER_HANDOVER, 0)
            socket.setsockopt(zmq.SNDHWM, self.config.send_hwm)
            socket.setsockopt(zmq.RCVHWM, self.config.receive_hwm)
            socket.setsockopt(zmq.MAXMSGSIZE, max_size)
            socket.bind(endpoint)
            return socket
        except BaseException:
            socket.close(linger=0)
            raise

    async def start(self) -> str:
        if self.context is not None:
            raise RuntimeError("relay already started")
        self.context = zmq.Context()
        try:
            self.socket = self._socket(self.config.endpoint, self.config.max_payload_bytes + 4096)
            self.endpoint = self.socket.getsockopt(zmq.LAST_ENDPOINT).decode("ascii")
            self.admin_socket = self._socket(self.config.admin_endpoint, MAX_ADMIN_JSON)
            self.admin_endpoint = self.admin_socket.getsockopt(zmq.LAST_ENDPOINT).decode("ascii")
            return self.endpoint
        except BaseException:
            await self.close()
            raise

    def _remove(self, registration: _Registration) -> None:
        if self._names.get(registration.name) is registration:
            del self._names[registration.name]
        if self._addresses.get(registration.address) is registration:
            del self._addresses[registration.address]

    def _expire(self) -> None:
        now = time.monotonic()
        for registration in tuple(self._names.values()):
            if registration.expires <= now:
                self._remove(registration)

    @staticmethod
    async def _queue(socket: zmq.asyncio.Socket, frames: list[bytes]) -> str | None:
        try:
            await socket.send_multipart(frames, flags=zmq.DONTWAIT)
        except zmq.Again:
            return "destination_full"
        except zmq.ZMQError as exc:
            if exc.errno == zmq.EHOSTUNREACH:
                return "destination_unavailable"
            raise
        return None

    async def _emit(self, address: bytes, *frames: bytes) -> str | None:
        assert self.socket is not None
        return await self._queue(self.socket, [address, VERSION, *frames])

    async def _error(self, address: bytes, token: bytes, request: bytes, code: str) -> None:
        # Lost/full control receipt => timeout/uncertain effect, never replay.
        await self._emit(address, ERROR, token, request, code.encode("ascii"))

    async def _hello(self, address: bytes, frames: list[bytes]) -> None:
        if len(frames) != 2 or not 1 <= len(frames[0]) <= 64:
            return
        request, encoded_name = frames
        name = _name(encoded_name)
        if name is None:
            await self._error(address, b"", request, "invalid_name")
            return
        if self.config.allowed_names is not None and name not in self.config.allowed_names:
            await self._error(address, b"", request, "admission_denied")
            return
        if name in self._names or address in self._addresses:
            await self._error(address, b"", request, "duplicate_name")
            return
        memberships = (
            {DEFAULT_NETWORK}
            if self.config.networks[DEFAULT_NETWORK].join_verifier is None else set()
        )
        registration = _Registration(
            name, address, secrets.token_hex(16).encode("ascii"),
            time.monotonic() + self.config.lease_seconds, memberships,
        )
        self._names[name] = registration
        self._addresses[address] = registration
        error = await self._emit(
            address, OK, b"", request, registration.token,
            str(self.config.lease_seconds).encode("ascii"),
            str(self.config.max_payload_bytes).encode("ascii"),
            json.dumps(sorted(memberships), separators=(",", ":")).encode("ascii"),
        )
        if error is not None:
            self._remove(registration)

    async def _handle(self, packet: list[zmq.Frame]) -> None:
        if len(packet) < 3 or bytes(packet[1]) != VERSION:
            return  # Strict version rejection; no legacy insecure success/fallback.
        address, command = bytes(packet[0]), bytes(packet[2])
        if len(packet) > 8:
            # Bound copying; correlated rejection only after incarnation validation.
            frames = [bytes(frame) for frame in packet[3:5]]
            command = b"INVALID"
        else:
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
        if command in (JOIN, LEAVE) and request:
            await self._membership(registration, command, request, frames)
            return
        if command != SEND or len(frames) != 5 or not request:
            if request:
                await self._error(address, token, request, "invalid_command")
            return
        network, destination, payload = _name(frames[2]), _name(frames[3]), frames[4]
        target = self._names.get(destination) if destination is not None else None
        if network is None:
            error = "invalid_network"
        elif destination is None:
            error = "invalid_destination"
        elif len(payload) > self.config.max_payload_bytes:
            error = "payload_too_large"
        elif network not in self.config.networks:
            error = "network_not_found"
        elif network not in registration.memberships:
            error = "not_member"
        elif target is None:
            error = "destination_unavailable"
        elif network not in target.memberships:
            error = "destination_not_member"
        elif not self.config.permits(registration.name, destination):
            error = "route_denied"
        else:
            error = await self._emit(
                target.address, DATA, target.token, network.encode("ascii"),
                registration.name.encode("ascii"), payload,
            )
        if error is None:
            await self._emit(address, OK, token, request)
        else:
            await self._error(address, token, request, error)

    async def _membership(
        self, registration: _Registration, command: bytes, request: bytes, frames: list[bytes],
    ) -> None:
        expected = 4 if command == JOIN else 3
        network = _name(frames[2]) if len(frames) == expected else None
        if len(frames) != expected:
            error = "invalid_command"
        elif network is None:
            error = "invalid_network"
        elif network not in self.config.networks:
            error = "network_not_found"
        else:
            error = None
        if error is not None:
            await self._error(registration.address, registration.token, request, error)
            return
        if command == JOIN:
            credential = None
            if frames[3]:
                if len(frames[3]) > MAX_CREDENTIAL_BYTES:
                    await self._error(
                        registration.address, registration.token, request, "join_denied"
                    )
                    return
                try:
                    credential = frames[3].decode("ascii")
                except UnicodeError:
                    credential = ""
                if not valid_credential(credential):
                    await self._error(
                        registration.address, registration.token, request, "join_denied"
                    )
                    return
            if not self.store.join_allowed(network, credential):
                await self._error(registration.address, registration.token, request, "join_denied")
                return
            changed = network not in registration.memberships
            registration.memberships.add(network)
        else:
            changed = network in registration.memberships
            registration.memberships.discard(network)
        await self._emit(
            registration.address, OK, registration.token, request,
            network.encode("ascii"), b"1" if changed else b"0",
        )

    def _sync_memberships(self, config: RelayConfig) -> None:
        # Policy/rotation never evicts; only networks actually deleted disappear.
        for registration in self._names.values():
            registration.memberships.intersection_update(config.networks)

    async def _admin_response(
        self, address: bytes, request: bytes, command: bytes, body: dict,
    ) -> None:
        assert self.admin_socket is not None
        encoded = json.dumps(body, separators=(",", ":"), allow_nan=False).encode("utf-8")
        if len(encoded) > MAX_ADMIN_JSON:
            command = ERROR
            encoded = json.dumps({
                "code": "response_too_large", "outcome": "no_effect",
                "revision": self.store.revision,
            }, separators=(",", ":")).encode("ascii")
        await self._queue(self.admin_socket, [address, ADMIN_VERSION, request, command, encoded])

    async def _handle_admin(self, packet: list[zmq.Frame]) -> None:
        if len(packet) < 3 or bytes(packet[1]) != ADMIN_VERSION:
            return
        address, request = bytes(packet[0]), bytes(packet[2])
        if not 1 <= len(request) <= 64:
            return
        try:
            if len(packet) != 5:
                raise _AdminRejection("invalid_request")
            if len(packet[3]) > MAX_CREDENTIAL_BYTES:
                raise _AdminRejection("unauthorized")
            try:
                token = bytes(packet[3]).decode("ascii")
            except UnicodeError:
                token = ""
            if not valid_credential(token) or not self.store.authenticate_admin(token):
                raise _AdminRejection("unauthorized")
            try:
                value = json_object(bytes(packet[4]))
            except ValueError:
                raise _AdminRejection("invalid_request") from None
            op, args = value.get("op"), value.get("args")
            if not isinstance(op, str) or op not in ADMIN_READS | ADMIN_MUTATIONS:
                raise _AdminRejection("invalid_request")
            if not isinstance(args, dict):
                raise _AdminRejection("invalid_request")
            mutation = op in ADMIN_MUTATIONS
            if set(value) != ({"op", "args", "expected_revision"} if mutation else {"op", "args"}):
                raise _AdminRejection("invalid_request")
            if mutation:
                revision = value["expected_revision"]
                if type(revision) is not int or not 0 <= revision <= 2**53 - 1:
                    raise _AdminRejection("invalid_request")
                if revision != self.store.revision:
                    raise _AdminRejection("revision_conflict")
            result = self._admin_operation(op, args, value.get("expected_revision"))
        except PersistenceIndeterminate as exc:
            self._sync_memberships(exc.committed_config)
            await self._admin_response(address, request, ERROR, {
                "code": exc.code, "outcome": exc.outcome, "revision": exc.revision,
            })
        except ConfigStoreError as exc:
            await self._admin_response(address, request, ERROR, {
                "code": exc.code, "outcome": exc.outcome, "revision": exc.revision,
            })
        except _AdminRejection as exc:
            await self._admin_response(address, request, ERROR, {
                "code": exc.code, "outcome": "no_effect", "revision": self.store.revision,
            })
        except ValueError:
            await self._admin_response(address, request, ERROR, {
                "code": "invalid_policy", "outcome": "no_effect", "revision": self.store.revision,
            })
        else:
            await self._admin_response(address, request, OK, {
                "revision": self.store.revision, "result": result,
            })

    @staticmethod
    def _keys(args: dict, required: set[str], optional: set[str] = frozenset()) -> None:
        if not required <= args.keys() or args.keys() - required - optional:
            raise _AdminRejection("invalid_request")

    @staticmethod
    def _credential(args: dict) -> str:
        token = args.get("credential")
        if not valid_credential(token):
            raise _AdminRejection("invalid_policy")
        return token

    def _admin_operation(self, op: str, args: dict, revision: int | None) -> dict:
        config = self.config
        if op == "config.get":
            self._keys(args, set())
            return self.store.redacted()
        if op == "network.list":
            self._keys(args, set())
            return {"networks": [
                {"network": name, "protected": config.networks[name].join_verifier is not None}
                for name in sorted(config.networks)
            ]}
        if op == "admin.rotate":
            self._keys(args, {"credential"})
            self.store.rotate_admin(self._credential(args), expected_revision=revision)
            return {"admin_source": "config"}
        if op == "network.create":
            self._keys(args, {"network"}, {"credential"})
        elif op == "network.update":
            self._keys(args, {"network", "protected"}, {"credential"})
        elif op == "network.rotate":
            self._keys(args, {"network", "credential"})
        elif op == "member.remove":
            self._keys(args, {"network", "name"})
        else:
            self._keys(args, {"network"})
        network = args["network"]
        if not valid_name(network):
            raise _AdminRejection("invalid_request")
        if op == "network.create":
            if network in config.networks:
                raise _AdminRejection("network_exists")
            verifier = make_verifier(self._credential(args)) if "credential" in args else None
            policy = NetworkConfig(join_verifier=verifier)
        else:
            if network not in config.networks:
                raise _AdminRejection("network_not_found")
            policy = config.networks[network]
        description = {"network": network, "protected": policy.join_verifier is not None}
        if op == "network.get":
            return description
        if op == "member.list":
            return {"network": network, "members": sorted(
                peer.name for peer in self._names.values() if network in peer.memberships
            )}
        if op == "member.remove":
            name = args["name"]
            if not valid_name(name):
                raise _AdminRejection("invalid_request")
            peer = self._names.get(name)
            changed = peer is not None and network in peer.memberships
            if peer is not None:
                peer.memberships.discard(network)
            return {"network": network, "name": name, "changed": changed, "ephemeral": True}
        if op == "network.delete":
            if network == DEFAULT_NETWORK:
                raise _AdminRejection("reserved_network")
            policies = dict(config.networks)
            del policies[network]
            committed = self.store.commit(
                replace(config, networks=policies), expected_revision=revision
            )
            self._sync_memberships(committed)
            return {"network": network, "deleted": True}
        if op == "network.rotate":
            if policy.join_verifier is None:
                raise _AdminRejection("invalid_policy")
            policy = NetworkConfig(join_verifier=make_verifier(self._credential(args)))
        if op == "network.update":
            if type(args["protected"]) is not bool:
                raise _AdminRejection("invalid_policy")
            if not args["protected"]:
                if "credential" in args:
                    raise _AdminRejection("invalid_policy")
                policy = NetworkConfig()
            elif "credential" in args:
                policy = NetworkConfig(join_verifier=make_verifier(self._credential(args)))
            elif policy.join_verifier is None:
                raise _AdminRejection("credential_required")
        policies = {**config.networks, network: policy}
        self.store.commit(replace(config, networks=policies), expected_revision=revision)
        return {"network": network, "protected": policy.join_verifier is not None}

    async def run(self) -> None:
        if (self.socket is None or self.socket.closed or self.admin_socket is None
                or self.admin_socket.closed):
            raise RuntimeError("start the relay before run()")
        if self._running:
            raise RuntimeError("relay is already running")
        self._running = True
        poller = zmq.asyncio.Poller()
        poller.register(self.socket, zmq.POLLIN)
        poller.register(self.admin_socket, zmq.POLLIN)
        try:
            while True:
                self._expire()
                events = dict(await poller.poll(
                    timeout=max(1, int(self.config.lease_seconds * 100))
                ))
                self._expire()
                # A bounded one-packet turn per socket prevents a peer flood from
                # starving administration and makes forwarding/removal cutoffs clear.
                if self.admin_socket in events:
                    await self._handle_admin(await self.admin_socket.recv_multipart(copy=False))
                if self.socket in events:
                    await self._handle(await self.socket.recv_multipart(copy=False))
        finally:
            self._running = False
            poller.unregister(self.socket)
            poller.unregister(self.admin_socket)

    async def close(self) -> None:
        if self._running:
            raise RuntimeError("cancel and await run() before closing the relay")
        for socket in (self.socket, self.admin_socket):
            if socket is not None:
                socket.close(linger=0)
        if self.context is not None:
            self.context.term()
        self._names.clear()
        self._addresses.clear()

    async def __aenter__(self) -> "Relay":
        await self.start()
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
