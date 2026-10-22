"""Private wire vocabulary; application payloads remain opaque bytes."""

import re

VERSION = b"AR2"
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


def valid_name(name: str) -> bool:
    return isinstance(name, str) and _NAME.fullmatch(name) is not None


def valid_credential(credential: object) -> bool:
    """Shared wire bound; verification/hashing belongs to credentials.py."""
    return (
        isinstance(credential, str)
        and 1 <= len(credential) <= MAX_CREDENTIAL_BYTES
        and all(0x21 <= ord(char) <= 0x7E for char in credential)
    )


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
