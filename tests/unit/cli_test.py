import base64
import io
import json
from types import SimpleNamespace

import pytest

from nodalwire.cli import (
    CLIInputError,
    CLIOutputLimit,
    _bounded_read,
    _decode_incoming,
    _env_token,
    _message_event,
    _OutputBudget,
    _positive_deadline,
    _read_payload,
)


def test_bounded_input_binary_empty_and_exact_limit(tmp_path):
    for payload in (b"", b"\x00\xff\n", b"a" * 9):
        assert _bounded_read(io.BytesIO(payload), len(payload)) == payload
    with pytest.raises(CLIInputError, match="exceeds byte limit"):
        _bounded_read(io.BytesIO(b"toolong"), 3)
    path = tmp_path / "payload.bin"
    path.write_bytes(b"\0\xff")
    assert _read_payload(path, 2) == b"\0\xff"
    with pytest.raises(CLIInputError, match="^cannot read input$"):
        _read_payload(tmp_path / "missing", 8)


def test_input_read_never_requests_unbounded_bytes():
    class Chunked:
        calls = []
        remaining = b"abcd"

        def read(self, count):
            self.calls.append(count)
            result = self.remaining[:1]
            self.remaining = self.remaining[1:]
            return result

    source = Chunked()
    assert _bounded_read(source, 4) == b"abcd"
    assert source.calls == [5, 4, 3, 2, 1]


@pytest.mark.parametrize("maximum", [-1, True, 16 * 1024 * 1024 + 1, "4"])
def test_invalid_input_limits_rejected(maximum):
    with pytest.raises(CLIInputError):
        _bounded_read(io.BytesIO(), maximum)


def test_environment_credentials_not_echoed(monkeypatch):
    assert _env_token(None) is None
    with pytest.raises(CLIInputError):
        _env_token(None, required=True)
    monkeypatch.setenv("CLI_JOIN_FIXTURE", "printable-test-token")
    assert _env_token("CLI_JOIN_FIXTURE") == "printable-test-token"
    for value in ("", "unsafe fixture secret", "é"):
        monkeypatch.setenv("CLI_JOIN_FIXTURE", value)
        with pytest.raises(CLIInputError) as error:
            _env_token("CLI_JOIN_FIXTURE")
        assert value not in str(error.value) if value else True
    monkeypatch.delenv("CLI_JOIN_FIXTURE")
    with pytest.raises(CLIInputError):
        _env_token("CLI_JOIN_FIXTURE")


@pytest.mark.parametrize("deadline", [0, -1, True, float("nan"), float("inf"), 3601, 10**1000])
def test_deadline_validation(deadline):
    with pytest.raises(CLIInputError):
        _positive_deadline(deadline)


def test_valid_deadline():
    assert _positive_deadline(5) == 5.0


def test_received_metadata_roundtrip_and_base64_output():
    message = SimpleNamespace(network="red", sender="alice", payload=b"\0\xff\x1b[31m")
    event = _message_event(message)
    assert event == {
        "event": "message",
        "network": "red",
        "sender": "alice",
        "payload": base64.b64encode(message.payload).decode("ascii"),
    }
    incoming = _decode_incoming(json.dumps(event).encode(), 1024)
    assert (incoming.network, incoming.sender, incoming.payload) == (
        "red",
        "alice",
        message.payload,
    )
    assert "\x1b" not in json.dumps(event)


@pytest.mark.parametrize(
    "data",
    [
        b"not-json-private-payload",
        b"[]",
        b"null",
        b"{}",
        b"\xff",
        b'{"event":"message","network":"red","network":"blue","sender":"a","payload":""}',
        b'{"event":"message","network":"red","sender":"a","payload":"/x=="}',
        b'{"event":"reply","network":"red","sender":"a","payload":""}',
        b'{"event":"message","network":"bad network","sender":"a","payload":""}',
        b'{"event":"message","network":"red","sender":"a","payload":false}',
    ],
)
def test_untrusted_reply_input_rejected_without_echo(data):
    with pytest.raises(CLIInputError, match="^invalid incoming message JSON$"):
        _decode_incoming(data, 100)


def test_deeply_nested_reply_metadata_is_safe_input_error():
    with pytest.raises(CLIInputError, match="^invalid incoming message JSON$"):
        _decode_incoming(b"[" * 2000 + b"0" + b"]" * 2000, 1024)


def test_reply_metadata_payload_bound():
    event = _message_event(SimpleNamespace(network="red", sender="a", payload=b"a" * 4))
    with pytest.raises(CLIInputError):
        _decode_incoming(json.dumps(event).encode(), 3)


def test_output_budget_count_and_byte_cutoff_are_explicit():
    stream = io.StringIO()
    output = _OutputBudget(max_count=1, max_bytes=100, stream=stream)
    output.emit({"event": "message"})
    assert output.count == 1
    assert output.bytes == len(stream.getvalue().encode())
    with pytest.raises(CLIOutputLimit, match="uncertain"):
        output.emit({"event": "message"})
    assert stream.getvalue().count("\n") == 1
    tiny = _OutputBudget(max_count=64, max_bytes=1, stream=stream)
    with pytest.raises(CLIOutputLimit):
        tiny.emit({"event": "message"})
    assert tiny.count == 0


@pytest.mark.parametrize(
    "count,size", [(0, 1), (True, 1), (1025, 1), (1, 0), (1, True), (1, 2**30)]
)
def test_invalid_output_bounds(count, size):
    with pytest.raises(CLIInputError):
        _OutputBudget(max_count=count, max_bytes=size)


def test_stdout_failure_is_not_swallowed():
    class Broken:
        def write(self, value):
            raise BrokenPipeError("fixture pipe closed")

    output = _OutputBudget(max_count=1, max_bytes=100, stream=Broken())
    with pytest.raises(BrokenPipeError):
        output.emit({"event": "message"})
    assert output.count == 0
