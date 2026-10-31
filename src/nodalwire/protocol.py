"""Private wire vocabulary; application payloads remain opaque bytes."""

import json
import math
import re

VERSION = b"NWM3"
ADMIN_VERSION = b"NA1"
DEFAULT_NETWORK = "default"
MAX_ADMIN_JSON = 65_536
MAX_CREDENTIAL_BYTES = 1024
HELLO = b"HELLO"
SEND = b"SEND"
JOIN = b"JOIN"
LEAVE = b"LEAVE"
HEARTBEAT = b"HEARTBEAT"
CLOSE = b"CLOSE"
OK = b"OK"
ERROR = b"ERROR"
DATA = b"DATA"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")
_MESSAGE_ID = re.compile(rb"[0-9a-f]{32}\Z")


def valid_message_id(frame: bytes) -> bool:
    """Validate native message metadata, never create or normalize an ID."""
    return isinstance(frame, bytes) and _MESSAGE_ID.fullmatch(frame) is not None


def valid_name(name: str) -> bool:
    return isinstance(name, str) and _NAME.fullmatch(name) is not None


def valid_credential(credential: object) -> bool:
    """Shared wire bound; verification/hashing belongs to credentials.py."""
    return (
        isinstance(credential, str)
        and 1 <= len(credential) <= MAX_CREDENTIAL_BYTES
        and all(0x21 <= ord(char) <= 0x7E for char in credential)
    )


def json_object(data: bytes, *, max_bytes: int = MAX_ADMIN_JSON) -> dict:
    """Strict bounded JSON object for control traffic; never interpolate input."""
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = value
        return result

    def nonfinite(value):
        raise ValueError("nonfinite JSON value")

    def finite_float(value):
        result = float(value)
        if not math.isfinite(result):
            raise ValueError("nonfinite JSON value")
        return result

    if len(data) > max_bytes:
        raise ValueError("JSON size limit exceeded")
    try:
        result = json.loads(
            data.decode("utf-8"), object_pairs_hook=unique,
            parse_constant=nonfinite, parse_float=finite_float
        )
        if not isinstance(result, dict):
            raise ValueError("expected JSON object")
        return result
    except (ValueError, UnicodeError, RecursionError) as exc:
        raise ValueError("invalid JSON object") from exc


class RelayError(Exception):
    """Relay status: Router rejection, local rejection or lifecycle interruption.

    Lifecycle codes closed/connection_failed can interrupt an already-sent request;
    they do not prove no effect. No status is a remote execution result.
    """

    def __init__(self, code: str):
        self.code = code
        super().__init__(code)


class ReceiptTimeout(TimeoutError):
    """No receipt arrived in time; the route's effect is uncertain. Never retry blindly."""
