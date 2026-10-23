"""Same-machine administrative transport, independent of peer networks/tokens.

Local bearer authentication is not encryption and does not protect root/same-user
memory inspection. A timeout/cancellation may follow an accepted mutation.
"""

import asyncio
import json
import math
import secrets
from dataclasses import dataclass

import zmq
import zmq.asyncio

from .config import local_endpoint
from .protocol import (
    ADMIN_VERSION,
    ERROR,
    MAX_ADMIN_JSON,
    OK,
    ReceiptTimeout,
    RelayError,
    json_object,
    valid_credential,
)

ADMIN_READS = frozenset({"config.get", "network.list", "network.get", "member.list"})
ADMIN_MUTATIONS = frozenset({
    "network.create", "network.update", "network.rotate", "network.delete",
    "member.remove", "admin.rotate",
})
ADMIN_ERRORS = frozenset({
    "invalid_request", "unauthorized", "revision_conflict", "network_not_found",
    "network_exists", "reserved_network", "invalid_policy", "credential_required",
    "environment_managed", "persistence_failed", "persistence_indeterminate",
    "response_too_large",
})


def _revision(value: object) -> bool:
    return type(value) is int and 0 <= value <= 2**53 - 1


def _seconds(value: float) -> float:
    if type(value) not in (int, float) or not math.isfinite(value) or value <= 0:
        raise ValueError("timeout must be finite and positive")
    return value


@dataclass(frozen=True)
class AdminReceipt:
    revision: int
    result: dict


class AdminError(RelayError):
    """Safe structured rejection. Indeterminate means never blindly retry."""

    def __init__(self, code: str, outcome: str, revision: int):
        super().__init__(code)
        self.outcome = outcome
        self.revision = revision


class AdminClient:
    """One owned DEALER, one outstanding call, no retries or hidden state.

    connect() sets up transport only; each call authenticates separately. It does
    not register a peer or prove authentication before a successful call receipt.
    """

    def __init__(self, endpoint: str, *, token: str, timeout: float = 5.0):
        endpoint = local_endpoint(endpoint)
        _seconds(timeout)
        if not valid_credential(token):
            raise ValueError("invalid admin credential")
        self.endpoint = endpoint
        self.timeout = timeout
        self._token = token.encode("ascii")
        self._closed = False
        self._pending = False
        self.context = zmq.asyncio.Context()
        self.socket = self.context.socket(zmq.DEALER)
        self.socket.setsockopt(zmq.LINGER, 0)
        self.socket.setsockopt(zmq.IMMEDIATE, 1)
        self.socket.setsockopt(zmq.IPV6, int(endpoint.startswith("tcp://[")))
        self.socket.setsockopt(zmq.IDENTITY, secrets.token_bytes(16))
        self.socket.setsockopt(zmq.SNDHWM, 1)
        self.socket.setsockopt(zmq.RCVHWM, 1)
        self.socket.setsockopt(zmq.MAXMSGSIZE, MAX_ADMIN_JSON)
        try:
            self.socket.connect(endpoint)
        except BaseException:
            self.socket.close(linger=0)
            self.context.term()
            raise

    @classmethod
    async def connect(
        cls, endpoint: str = "tcp://127.0.0.1:5556", *, token: str, timeout: float = 5.0,
    ) -> "AdminClient":
        return cls(endpoint, token=token, timeout=timeout)

    async def call(
        self, op: str, args: dict | None = None, *, expected_revision: int | None = None,
        timeout: float | None = None,
    ) -> AdminReceipt:
        if self._closed:
            raise RelayError("closed")
        if self._pending:
            raise RelayError("pending_full")
        seconds = _seconds(self.timeout if timeout is None else timeout)
        if op not in ADMIN_READS | ADMIN_MUTATIONS:
            raise ValueError("invalid admin operation")
        if args is not None and not isinstance(args, dict):
            raise TypeError("admin args must be an object")
        request = {"op": op, "args": {} if args is None else args}
        if op in ADMIN_MUTATIONS:
            if not _revision(expected_revision):
                raise ValueError("mutation requires expected_revision")
            request["expected_revision"] = expected_revision
        elif expected_revision is not None:
            raise ValueError("read does not accept expected_revision")
        try:
            encoded = json.dumps(request, separators=(",", ":"), allow_nan=False).encode("utf-8")
        except (ValueError, TypeError, UnicodeError, RecursionError) as exc:
            raise ValueError("invalid admin request JSON") from exc
        if len(encoded) > MAX_ADMIN_JSON:
            raise ValueError("admin request size limit exceeded")
        identity = secrets.token_hex(16).encode("ascii")
        self._pending = True
        try:
            async with asyncio.timeout(seconds):
                await self.socket.send_multipart([ADMIN_VERSION, identity, self._token, encoded])
                while True:
                    frames = await self.socket.recv_multipart()
                    if len(frames) < 2 or frames[0] != ADMIN_VERSION or frames[1] != identity:
                        continue  # Ignore stale receipt, never retry a mutation.
                    if len(frames) != 4:
                        raise RelayError("invalid_receipt")
                    try:
                        value = json_object(frames[3])
                    except ValueError as exc:
                        raise RelayError("invalid_receipt") from exc
                    if not _revision(value.get("revision")):
                        raise RelayError("invalid_receipt")
                    if frames[2] == OK and set(value) == {"revision", "result"}:
                        if not isinstance(value["result"], dict):
                            raise RelayError("invalid_receipt")
                        return AdminReceipt(value["revision"], value["result"])
                    if (frames[2] == ERROR and set(value) == {"revision", "code", "outcome"}
                            and isinstance(value["code"], str) and value["code"] in ADMIN_ERRORS
                            and value["outcome"] == (
                                "indeterminate" if value["code"] == "persistence_indeterminate"
                                else "no_effect"
                            )):
                        raise AdminError(value["code"], value["outcome"], value["revision"])
                    raise RelayError("invalid_receipt")
        except TimeoutError as exc:
            raise ReceiptTimeout("admin receipt timed out; effect uncertain") from exc
        except zmq.ZMQError as exc:
            raise RelayError("closed" if self._closed else "connection_failed") from exc
        finally:
            self._pending = False

    async def close(self) -> None:
        if not self._closed:
            self._closed = True
            self.socket.close(linger=0)
            self.context.term()
            self._token = b""

    async def __aenter__(self) -> "AdminClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.close()
