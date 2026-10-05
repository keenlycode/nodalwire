"""Private wire vocabulary; application payloads remain opaque bytes."""

import re

VERSION = b"AR1"
HELLO = b"HELLO"
SEND = b"SEND"
HEARTBEAT = b"HEARTBEAT"
CLOSE = b"CLOSE"
OK = b"OK"
ERROR = b"ERROR"
DATA = b"DATA"
_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9_.-]{0,127}\Z")


def valid_name(name: str) -> bool:
    return isinstance(name, str) and _NAME.fullmatch(name) is not None


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
