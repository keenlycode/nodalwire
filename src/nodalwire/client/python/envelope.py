"""Optional client-layer correlation format. The relay never interprets this format."""

import base64
import binascii
import json
import re
from dataclasses import dataclass
from typing import Literal

from ...protocol import RelayError

_PREFIX = b"NWR1\n"
_ID = re.compile(r"[0-9a-f]{32}\Z")
_DEFAULT_LIMIT = 1_048_576


@dataclass(frozen=True)
class Envelope:
    kind: Literal["request", "reply"]
    id: str
    payload: bytes


def _limit(value: int) -> None:
    if type(value) is not int or value <= 0:
        raise ValueError("max_bytes must be a positive integer")


def encode_envelope(envelope: Envelope, *, max_bytes: int = _DEFAULT_LIMIT) -> bytes:
    """Encode arbitrary bytes; the complete envelope must fit the selected limit."""
    _limit(max_bytes)
    if not isinstance(envelope, Envelope):
        raise TypeError("expected Envelope")
    if envelope.kind not in ("request", "reply"):
        raise ValueError("invalid envelope kind")
    if not isinstance(envelope.id, str) or _ID.fullmatch(envelope.id) is None:
        raise ValueError("invalid envelope id")
    if not isinstance(envelope.payload, bytes):
        raise TypeError("envelope payload must be bytes")
    # Check encoded size before allocating a base64/JSON copy of an oversized input.
    overhead = len(_PREFIX) + len(json.dumps(
        {"v": 1, "kind": envelope.kind, "id": envelope.id, "payload": ""},
        separators=(",", ":"),
    ))
    if overhead + 4 * ((len(envelope.payload) + 2) // 3) > max_bytes:
        raise RelayError("payload_too_large")
    return _PREFIX + json.dumps(
        {"v": 1, "kind": envelope.kind, "id": envelope.id,
         "payload": base64.b64encode(envelope.payload).decode("ascii")},
        separators=(",", ":"),
    ).encode("utf-8")


def _unique(pairs: list[tuple[str, object]]) -> dict:
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate envelope key")
        result[key] = value
    return result


def decode_envelope(payload: bytes, *, max_bytes: int = _DEFAULT_LIMIT) -> Envelope | None:
    """Return None for non-envelopes, including malformed/unsupported envelopes.

    Callers retain the original ordinary message on None, never silently discard it.
    """
    _limit(max_bytes)
    if not isinstance(payload, bytes):
        raise TypeError("payload must be bytes")
    if len(payload) > max_bytes or not payload.startswith(_PREFIX):
        return None
    try:
        value = json.loads(payload[len(_PREFIX):].decode("utf-8"), object_pairs_hook=_unique)
        if (
            not isinstance(value, dict)
            or set(value) != {"v", "kind", "id", "payload"}
            or type(value["v"]) is not int
            or value["v"] != 1
            or value["kind"] not in ("request", "reply")
            or not isinstance(value["id"], str)
            or _ID.fullmatch(value["id"]) is None
            or not isinstance(value["payload"], str)
        ):
            return None
        encoded = value["payload"].encode("ascii")
        decoded = base64.b64decode(encoded, validate=True)
        if base64.b64encode(decoded) != encoded:
            return None
        return Envelope(value["kind"], value["id"], decoded)
    except (ValueError, TypeError, UnicodeError, binascii.Error, RecursionError):
        return None
