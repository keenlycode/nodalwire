import base64
from dataclasses import FrozenInstanceError

import pytest

from nodalwire.config import RelayConfig
from nodalwire.credentials import (
    make_verifier,
    resolve_admin_credential,
    validate_token,
    validate_verifier,
    verify_token,
)


@pytest.fixture(scope="module")
def verifier():
    return make_verifier("fixture-admin-token")


def test_verifier_fixed_supported_format_and_random_salt(verifier):
    assert len(verifier) == 79
    prefix, salt, digest = verifier.split("$")
    assert prefix == "scrypt-v1"
    assert len(base64.b64decode(salt, validate=True)) == 16
    assert len(base64.b64decode(digest, validate=True)) == 32
    assert validate_verifier(verifier) == verifier
    assert verify_token("fixture-admin-token", verifier)
    assert not verify_token("wrong-token", verifier)
    assert verifier != make_verifier("fixture-admin-token")
    assert "fixture-admin-token" not in verifier


@pytest.mark.parametrize(
    "token", [None, 1, b"bytes", "", "has space", "\t", "\n", "\r", "\0", "é", "a" * 1025]
)
def test_invalid_tokens_fail_without_echo(token, verifier):
    with pytest.raises(ValueError, match="^invalid credential format$"):
        make_verifier(token)
    assert not verify_token(token, verifier)


def test_token_boundaries(verifier):
    assert validate_token("!") == "!"
    assert validate_token("~" * 1024) == "~" * 1024
    assert verify_token("!", make_verifier("!"))


@pytest.mark.parametrize(
    "value", [None, 1, "", "scrypt-v2$bad", "x" * 79, "scrypt-v1$" + "A" * 24 + "$" + "A" * 44]
)
def test_malformed_verifiers_fail_closed(value):
    with pytest.raises(ValueError, match="credential verifier"):
        validate_verifier(value)
    with pytest.raises(ValueError):
        RelayConfig(admin_verifier=value if value is not None else "invalid")


def test_noncanonical_base64_rejected(verifier):
    prefix, salt, digest = verifier.split("$")
    # Last salt byte has only two significant base64 bits; change unused padding bits.
    alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789+/"
    changed = alphabet[alphabet.index(salt[-3]) + 1]
    noncanonical = f"{prefix}${salt[:-3]}{changed}==${digest}"
    with pytest.raises(ValueError):
        validate_verifier(noncanonical)


def test_environment_precedence_no_fallback_and_redacted_repr(verifier):
    config = RelayConfig(admin_verifier=verifier)
    selected = resolve_admin_credential(config, {"NODALWIRE_ADMIN_TOKEN": "environment-token"})
    assert selected.source == "environment"
    assert verify_token("environment-token", selected.verifier)
    assert not verify_token("fixture-admin-token", selected.verifier)
    assert "environment-token" not in repr(selected)
    assert selected.verifier not in repr(selected)
    assert verifier not in repr(config)
    assert resolve_admin_credential(config, {}).source == "config"
    with pytest.raises(FrozenInstanceError):
        selected.source = "config"
    for token in ("", "bad token", "é"):
        with pytest.raises(ValueError):
            resolve_admin_credential(config, {"NODALWIRE_ADMIN_TOKEN": token})
    with pytest.raises(ValueError, match="administrator credential required"):
        resolve_admin_credential(RelayConfig(), {})
