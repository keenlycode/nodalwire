import pytest

from nodalwire.protocol import ADMIN_VERSION, VERSION, valid_credential, valid_message_id


def test_wire_version_and_credential_bounds():
    assert VERSION == b"NWM3"
    assert ADMIN_VERSION == b"NA1"
    assert valid_credential("!" * 1024)
    for value in (None, "", "x" * 1025, " ", "a\nb", "a\x00b", "é", "\ud800"):
        assert not valid_credential(value)


@pytest.mark.parametrize("value", [b"0" * 32, b"a" * 32, b"0123456789abcdef" * 2])
def test_valid_native_message_ids(value):
    assert valid_message_id(value)


@pytest.mark.parametrize("value", [
    None, "a" * 32, b"", b"a" * 31, b"a" * 33, b"A" * 32,
    b"g" * 32, b"\xff" * 32, b"a" * 31 + b"\n", b"a" * 32 + b"\n",
])
def test_invalid_native_message_ids(value):
    assert not valid_message_id(value)
