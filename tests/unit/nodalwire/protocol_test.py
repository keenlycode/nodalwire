from nodalwire.protocol import VERSION, valid_credential


def test_wire_version_and_credential_bounds():
    assert VERSION == b"AR2"
    assert valid_credential("!" * 1024)
    for value in (None, "", "x" * 1025, " ", "a\nb", "a\x00b", "é", "\ud800"):
        assert not valid_credential(value)
