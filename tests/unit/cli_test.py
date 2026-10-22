import asyncio
import base64
import io
import json
from types import SimpleNamespace

import pytest

from nodalwire.cli import (
    CLIInputError,
    CLIOutputLimit,
    _admin_arguments,
    _admin_revision,
    _bounded_read,
    _decode_incoming,
    _env_token,
    _message_event,
    _OutputBudget,
    _peer_operation,
    _positive_deadline,
    _read_payload,
    _request_with_events,
)
from nodalwire.protocol import RelayError


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


class _FakeNode:
    def __init__(self, messages=(), *, reply=None, error=None, pending=False):
        self.inbox = asyncio.Queue()
        for message in messages:
            self.inbox.put_nowait(message)
        self.result = reply
        self.error = error
        self.pending = pending
        self.cancelled = False
        self.calls = []

    async def request(self, destination, payload, *, network, timeout):
        self.calls.append((destination, payload, network, timeout))
        try:
            if self.pending:
                await asyncio.Future()
            if self.error is not None:
                raise self.error
            return self.result
        except asyncio.CancelledError:
            self.cancelled = True
            raise

    async def receive(self):
        return await self.inbox.get()

    def receive_nowait(self):
        try:
            return self.inbox.get_nowait()
        except asyncio.QueueEmpty:
            return None


def test_request_delegates_and_outputs_all_queued_unrelated_messages():
    async def run():
        messages = [
            SimpleNamespace(network="other", sender="eve", payload=bytes([i])) for i in range(4)
        ]
        reply = SimpleNamespace(network="red", sender="bob", payload=b"reply")
        node = _FakeNode(messages, reply=reply)
        stream = io.StringIO()
        output = _OutputBudget(max_count=64, max_bytes=10000, stream=stream)
        result = await _request_with_events(
            node, "bob", b"request", network="red", timeout=5, output=output
        )
        assert result is reply
        assert node.calls == [("bob", b"request", "red", 5)]
        assert [json.loads(line)["payload"] for line in stream.getvalue().splitlines()] == [
            base64.b64encode(message.payload).decode() for message in messages
        ]
        assert node.receive_nowait() is None

    asyncio.run(run())


def test_request_failure_still_emits_queued_unrelated_data():
    async def run():
        message = SimpleNamespace(network="other", sender="eve", payload=b"unrelated")
        node = _FakeNode([message], error=TimeoutError())
        output = _OutputBudget(max_count=64, max_bytes=10000, stream=io.StringIO())
        with pytest.raises(TimeoutError):
            await _request_with_events(node, "bob", b"", network="red", timeout=5, output=output)
        assert output.count == 1
        assert node.receive_nowait() is None

    asyncio.run(run())


def test_request_output_cap_cancels_owned_request_without_retry():
    async def run():
        messages = [
            SimpleNamespace(network="red", sender="eve", payload=b"noise") for _ in range(3)
        ]
        node = _FakeNode(messages, pending=True)
        output = _OutputBudget(max_count=1, max_bytes=10000, stream=io.StringIO())
        with pytest.raises(CLIOutputLimit, match="uncertain"):
            await _request_with_events(node, "bob", b"", network="red", timeout=5, output=output)
        assert node.cancelled
        assert len(node.calls) == 1
        assert output.count == 1

    asyncio.run(run())


def test_request_cutoff_preserves_receive_result_that_wins_cancellation():
    async def run():
        started = asyncio.Event()
        ordinary = SimpleNamespace(network="other", sender="eve", payload=b"owned-before-cutoff")
        reply = SimpleNamespace(network="red", sender="bob", payload=b"reply")

        class Peer(_FakeNode):
            async def receive(self):
                started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    return ordinary

            async def request(self, *args, **kwargs):
                await started.wait()
                return reply

        stream = io.StringIO()
        output = _OutputBudget(max_count=64, max_bytes=10000, stream=stream)
        result = await _request_with_events(
            Peer(),
            "bob",
            b"request",
            network="red",
            timeout=5,
            output=output,
        )
        assert result is reply
        assert output.count == 1
        assert (
            json.loads(stream.getvalue())["payload"] == base64.b64encode(ordinary.payload).decode()
        )
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())


@pytest.mark.parametrize("first_event", ["reply", "cancel", "deadline", "reject"])
@pytest.mark.parametrize("cleanup_cancels", [1, 2, 3])
def test_single_and_repeated_cleanup_cancel_preserves_first_event_and_owned_data(
    first_event, cleanup_cancels
):
    async def run():
        receiver_started = asyncio.Event()
        cleanup_started = asyncio.Event()
        release = asyncio.Event()
        reply = SimpleNamespace(network="red", sender="bob", payload=b"selected-reply")
        rejection = RelayError("destination_unavailable")
        ordinary = SimpleNamespace(network="other", sender="eve", payload=b"owned-ordinary")

        class Peer(_FakeNode):
            async def request(self, *args, **kwargs):
                await receiver_started.wait()
                if first_event == "reply":
                    return reply
                if first_event == "reject":
                    raise rejection
                return await super().request(*args, **kwargs)

            async def receive(self):
                receiver_started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    cleanup_started.set()
                    waiting = asyncio.create_task(release.wait())
                    while True:
                        try:
                            await asyncio.shield(waiting)
                            return ordinary
                        except asyncio.CancelledError:
                            pass

        peer = Peer(pending=True)
        stream = io.StringIO()
        deadline = asyncio.timeout(None)

        async def invoke():
            async with deadline:
                return await _request_with_events(
                    peer,
                    "bob",
                    b"request",
                    network="red",
                    timeout=1,
                    output=_OutputBudget(max_count=64, max_bytes=4096, stream=stream),
                )

        operation = asyncio.create_task(invoke())
        await receiver_started.wait()
        if first_event == "cancel":
            operation.cancel()
        elif first_event == "deadline":
            deadline.reschedule(asyncio.get_running_loop().time())
        await cleanup_started.wait()
        for _ in range(cleanup_cancels):
            operation.cancel()
            await asyncio.sleep(0)  # Explicit scheduling edge, not wallclock polling.
        release.set()
        if first_event == "reply":
            assert await operation is reply
        elif first_event == "reject":
            with pytest.raises(RelayError) as caught:
                await operation
            assert caught.value is rejection
        else:
            with pytest.raises(
                TimeoutError if first_event == "deadline" else asyncio.CancelledError
            ):
                await operation
            assert peer.cancelled
        if first_event != "cancel":
            assert operation.cancelling() == 0
        events = list(map(json.loads, stream.getvalue().splitlines()))
        assert len(events) == 1 and events[0]["sender"] == "eve"
        assert base64.b64decode(events[0]["payload"]) == b"owned-ordinary"
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())


@pytest.mark.parametrize("cleanup_cancels", [1, 2, 3])
def test_client_owned_reply_before_request_coroutine_cleanup_finishes_wins_cancel(cleanup_cancels):
    async def run():
        receiver_started = asyncio.Event()
        request_selected = asyncio.Event()
        receiver_cleanup = asyncio.Event()
        release = asyncio.Event()
        reply = SimpleNamespace(network="red", sender="bob", payload=b"client-owned-reply")
        ordinary = SimpleNamespace(network="other", sender="eve", payload=b"client-owned-ordinary")

        class Peer(_FakeNode):
            async def request(self, *args, **kwargs):
                await receiver_started.wait()
                request_selected.set()
                waiting = asyncio.create_task(release.wait())
                while True:
                    try:
                        await asyncio.shield(waiting)
                        return reply
                    except asyncio.CancelledError:
                        pass  # Models result-first library child cleanup.

            async def receive(self):
                receiver_started.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    receiver_cleanup.set()
                    waiting = asyncio.create_task(release.wait())
                    while True:
                        try:
                            await asyncio.shield(waiting)
                            return ordinary
                        except asyncio.CancelledError:
                            pass

        stream = io.StringIO()
        operation = asyncio.create_task(
            _request_with_events(
                Peer(),
                "bob",
                b"request",
                network="red",
                timeout=1,
                output=_OutputBudget(max_count=64, max_bytes=4096, stream=stream),
            )
        )
        await request_selected.wait()
        operation.cancel()  # Request coroutine not done, but client owns the reply.
        await receiver_cleanup.wait()
        for _ in range(cleanup_cancels):
            operation.cancel()
            await asyncio.sleep(0)
        release.set()
        assert await operation is reply
        assert operation.cancelling() == 0
        events = list(map(json.loads, stream.getvalue().splitlines()))
        assert len(events) == 1 and events[0]["sender"] == "eve"
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())


def test_request_caller_cancellation_settles_owned_tasks():
    async def run():
        started = asyncio.Event()

        class Peer(_FakeNode):
            async def request(self, *args, **kwargs):
                started.set()
                return await super().request(*args, **kwargs)

        node = Peer(pending=True)
        output = _OutputBudget(max_count=64, max_bytes=10000, stream=io.StringIO())
        task = asyncio.create_task(
            _request_with_events(
                node,
                "bob",
                b"",
                network="red",
                timeout=5,
                output=output,
            )
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await task
        assert node.cancelled
        assert len(asyncio.all_tasks()) == 1

    asyncio.run(run())


def test_admin_argument_shapes_and_revision_fences():
    assert _admin_arguments("config.get") == {}
    assert _admin_arguments("network.create", network="red") == {"network": "red"}
    assert _admin_arguments("network.update", network="red", protected=False) == {
        "network": "red",
        "protected": False,
    }
    assert _admin_arguments("member.remove", network="red", member="alice") == {
        "network": "red",
        "name": "alice",
    }
    _admin_revision("config.get", None)
    _admin_revision("member.remove", 0)
    for operation, kwargs in (
        ("unknown", {}),
        ("config.get", {"network": "red"}),
        ("network.rotate", {"network": "red"}),
        ("network.update", {"network": "red"}),
        ("network.update", {"network": "red", "protected": False, "credential": "secret"}),
        ("member.remove", {"network": "red"}),
    ):
        with pytest.raises(CLIInputError):
            _admin_arguments(operation, **kwargs)
    for operation, revision in (
        ("config.get", 1),
        ("admin.rotate", None),
        ("member.remove", True),
        ("network.create", 1 << 53),
    ):
        with pytest.raises(CLIInputError):
            _admin_revision(operation, revision)


def test_each_operation_joins_selected_network_and_reply_uses_incoming_network():
    async def run():
        class Peer(_FakeNode):
            async def join(self, network, credential, *, timeout):
                self.calls.append(("join", network, credential))

            async def send(self, destination, payload, *, network, timeout):
                self.calls.append(("send", destination, payload, network))

            async def reply(self, incoming, payload, *, timeout):
                self.calls.append(("reply", incoming.sender, payload, incoming.network))

        node = Peer()
        output = _OutputBudget(max_count=64, max_bytes=10000, stream=io.StringIO())
        result = await _peer_operation(
            node,
            "send",
            destination="bob",
            payload=b"binary",
            network="red",
            credential="join-token",
            timeout=5,
            count=1,
            output=output,
        )
        assert node.calls == [("join", "red", "join-token"), ("send", "bob", b"binary", "red")]
        assert result["meaning"] == "native_queue_acceptance_only"
        incoming = SimpleNamespace(network="blue", sender="alice", payload=b"request-envelope")
        await _peer_operation(
            node,
            "reply",
            destination=None,
            payload=b"reply",
            network="default",
            credential=None,
            timeout=5,
            count=1,
            output=output,
            incoming=incoming,
        )
        assert node.calls[-2:] == [("join", "blue", None), ("reply", "alice", b"reply", "blue")]

    asyncio.run(run())


def test_stdout_failure_is_not_swallowed():
    class Broken:
        def write(self, value):
            raise BrokenPipeError("fixture pipe closed")

    output = _OutputBudget(max_count=1, max_bytes=100, stream=Broken())
    with pytest.raises(BrokenPipeError):
        output.emit({"event": "message"})
    assert output.count == 0
