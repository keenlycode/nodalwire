import json

import pytest

from nodalwire.client.python.envelope import Envelope, decode_envelope, encode_envelope
from nodalwire.protocol import RelayError

ID = "0123456789abcdef" * 2


@pytest.mark.parametrize("kind", ["request", "reply"])
@pytest.mark.parametrize("payload", [b"", bytes(range(256)), b"\x00\xffopaque\n"])
def test_round_trip(kind, payload):
    value = Envelope(kind, ID, payload)
    wire = encode_envelope(value)
    assert wire.startswith(b"NWR1\n")
    assert decode_envelope(wire) == value
    assert encode_envelope(value, max_bytes=len(wire)) == wire
    assert decode_envelope(wire, max_bytes=len(wire) - 1) is None
    with pytest.raises(RelayError, match="payload_too_large"):
        encode_envelope(value, max_bytes=len(wire) - 1)


@pytest.mark.parametrize("raw", [
    b"", b"{}", b'NWR1\n[]', b'NWR1\nnull', b'NWR1\n\xff',
    b'NWR1\n{"v":1,"v":1,"kind":"request","id":"' + ID.encode() + b'","payload":""}',
    b'NWR1\n{"v":1,"\\u0076":1,"kind":"request","id":"' + ID.encode()
    + b'","payload":""}',
    b'NWR1\n' + b"[" * 2000 + b"]" * 2000,
])
def test_non_envelopes_stay_ordinary(raw):
    assert decode_envelope(raw) is None


@pytest.mark.parametrize("field,value", [
    ("v", True), ("v", 2), ("v", 1.0), ("kind", "event"), ("kind", []),
    ("id", ID.upper()), ("id", ID + "\n"), ("id", 42),
    ("payload", "Zg"), ("payload", "Zh=="), ("payload", "Zg==\n"),
    ("payload", "____"), ("payload", "☃"), ("payload", None),
])
def test_exact_field_types_and_canonical_base64(field, value):
    document = {"v": 1, "kind": "reply", "id": ID, "payload": "Zg=="}
    document[field] = value
    assert decode_envelope(b"NWR1\n" + json.dumps(document).encode()) is None


def test_exact_keys_and_encode_validation():
    document = {"v": 1, "kind": "reply", "id": ID, "payload": ""}
    for key in tuple(document):
        assert decode_envelope(b"NWR1\n" + json.dumps(
            {k: v for k, v in document.items() if k != key}
        ).encode()) is None
    document["extra"] = 1
    assert decode_envelope(b"NWR1\n" + json.dumps(document).encode()) is None
    for envelope in (Envelope("event", ID, b""), Envelope("request", "bad", b"")):
        with pytest.raises(ValueError):
            encode_envelope(envelope)
    with pytest.raises(TypeError):
        encode_envelope(Envelope("request", ID, "not bytes"))
    for limit in (0, True, -1):
        with pytest.raises(ValueError):
            decode_envelope(b"", max_bytes=limit)
