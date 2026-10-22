"""Bounded bearer verification, independent of peer names and membership state."""

import base64
import binascii
import hashlib
import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .config import RelayConfig

_PREFIX = "scrypt-v1"


def validate_token(token: str) -> str:
    """Validate the shared wire token format without echoing supplied material."""
    if not isinstance(token, str) or not 1 <= len(token) <= 1024:
        raise ValueError("invalid credential format")
    if any(not 0x21 <= ord(char) <= 0x7E for char in token):
        raise ValueError("invalid credential format")
    return token


def _decode_verifier(verifier: str) -> tuple[bytes, bytes]:
    if not isinstance(verifier, str) or len(verifier) != 79:
        raise ValueError("invalid credential verifier")
    parts = verifier.split("$")
    if len(parts) != 3 or parts[0] != _PREFIX:
        raise ValueError("unsupported credential verifier")
    decoded = []
    for encoded, size in zip(parts[1:], (16, 32), strict=True):
        try:
            value = base64.b64decode(encoded, validate=True)
        except (ValueError, binascii.Error):
            raise ValueError("invalid credential verifier") from None
        if len(value) != size or base64.b64encode(value).decode("ascii") != encoded:
            raise ValueError("invalid credential verifier")
        decoded.append(value)
    return decoded[0], decoded[1]


def validate_verifier(verifier: str) -> str:
    _decode_verifier(verifier)
    return verifier


def _derive(token: str, salt: bytes) -> bytes:
    return hashlib.scrypt(token.encode("ascii"), salt=salt, n=16384, r=8, p=1, dklen=32)


def make_verifier(token: str) -> str:
    validate_token(token)
    salt = os.urandom(16)
    digest = _derive(token, salt)
    encoded_salt = base64.b64encode(salt).decode("ascii")
    encoded_digest = base64.b64encode(digest).decode("ascii")
    return f"{_PREFIX}${encoded_salt}${encoded_digest}"


def verify_token(token: str, verifier: str) -> bool:
    salt, expected = _decode_verifier(verifier)
    try:
        validate_token(token)
    except ValueError:
        return False
    return hmac.compare_digest(_derive(token, salt), expected)


@dataclass(frozen=True)
class AdminCredential:
    verifier: str = field(repr=False)
    source: str


def resolve_admin_credential(
    config: "RelayConfig", environ: Mapping[str, str] | None = None
) -> AdminCredential:
    environment = os.environ if environ is None else environ
    if "NODALWIRE_ADMIN_TOKEN" in environment:
        return AdminCredential(make_verifier(environment["NODALWIRE_ADMIN_TOKEN"]), "environment")
    if config.admin_verifier is None:
        raise ValueError("administrator credential required via environment or configuration")
    return AdminCredential(validate_verifier(config.admin_verifier), "config")
