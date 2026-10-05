import asyncio
import time

import pytest

from nodalwire import Node, ReceiptTimeout, RelayError
from nodalwire.protocol import CLOSE, HEARTBEAT, HELLO, SEND, VERSION

from .helpers import raw_node, raw_request, running_relay


def test_heartbeats_keep_lease_alive_across_multiple_intervals():
    async def check():
        async with running_relay(lease_seconds=0.15) as h:
            alice = await h.node("alice")
            # Deliberately observe more than three lease periods, not an admission sleep.
            await asyncio.sleep(0.5)
            with pytest.raises(RelayError, match="duplicate_name"):
                await Node.connect("alice", h.endpoint)
            await alice.send("alice", b"alive")
            assert (await alice.receive()).payload == b"alive"

    asyncio.run(check())


def test_failed_admission_and_timeout_close_attempt_resources():
    async def check():
        observed = []

        class ObservedNode(Node):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, **kwargs)
                observed.append(self)

        async with running_relay() as h:
            await h.node("alice")
            with pytest.raises(RelayError, match="duplicate_name"):
                await ObservedNode.connect("alice", h.endpoint)
            # Native socket is bound but no run task consumes HELLO or emits replies.
            silent = h.relay.__class__(h.relay.config)
            endpoint = await silent.start()
            try:
                with pytest.raises(ReceiptTimeout):
                    await ObservedNode.connect("waiting", endpoint, timeout=0.05)
            finally:
                await silent.close()
            for node in observed:
                assert node.socket.closed and node.context.closed
                assert node._receiver.done() and node._heartbeat is None
                assert node._cleanup_task.done() and node._cleanup_done.is_set()
                assert not node._pending

    asyncio.run(check())


def test_localhost_connect_is_normalized_and_relays_bytes():
    async def check():
        async with running_relay() as h:
            node = await Node.connect("localhost", h.endpoint.replace("127.0.0.1", "localhost"))
            try:
                assert node.endpoint == h.endpoint
                await node.send("localhost", b"local\x00\xff")
                assert (await node.receive()).payload == b"local\x00\xff"
            finally:
                await node.close()
            assert node.socket.closed and node.context.closed

    asyncio.run(check())


def test_crash_reconnect_waits_for_expiry_no_takeover():
    async def check():
        lease = 0.25
        async with running_relay(lease_seconds=lease) as h:
            alice = await h.node("alice")
            old_token = alice._token
            # Intentional process-crash equivalent: close owned transport with no CLOSE.
            await alice._cleanup()
            with pytest.raises(RelayError, match="duplicate_name"):
                await Node.connect("alice", h.endpoint)
            # Admission receipt established the lease; wait its configured deadline.
            await asyncio.sleep(lease + 0.05)
            replacement = await h.node("alice")
            assert replacement._token != old_token
            await replacement.send("alice", b"new")
            assert (await replacement.receive()).payload == b"new"

    asyncio.run(check())


def test_old_tokens_cannot_close_send_or_refresh_reused_name_and_native_address():
    async def check():
        lease = 0.15
        async with running_relay(lease_seconds=lease) as h:
            observer = await h.node("observer")
            async with raw_node(h.endpoint, "alice", identity=b"reused-native-address") as (
                socket,
                old_token,
            ):
                # Raw test peer has no automatic heartbeats. Wait its established lease.
                await asyncio.sleep(lease + 0.05)
                reply = await raw_request(socket, HELLO, b"alice", initial=True)
                assert reply[1] == b"OK"
                new_token = reply[4]
                assert new_token != old_token
                for command, extra in ((CLOSE, ()), (SEND, (b"observer", b"stale"))):
                    reply = await raw_request(socket, command, old_token, *extra)
                    assert reply[-1] == b"not_registered"
                await socket.send_multipart([VERSION, HEARTBEAT, old_token])
                reply = await raw_request(socket, SEND, new_token, b"observer", b"fresh")
                assert reply[1] == b"OK"
                assert (await observer.receive()).payload == b"fresh"
                # Old heartbeat must not extend NEW token's lease.
                accepted_at = time.monotonic()
                while time.monotonic() < accepted_at + lease + 0.05:
                    await socket.send_multipart([VERSION, HEARTBEAT, old_token])
                    await asyncio.sleep(0.02)
                reply = await raw_request(socket, SEND, new_token, b"observer", b"expired")
                assert reply[-1] == b"not_registered"

    asyncio.run(check())


def test_receive_waiter_is_woken_and_resources_close_on_cancellation():
    async def check():
        async with running_relay() as h:
            alice = await h.node("alice")
            receive = asyncio.create_task(alice.receive())
            await alice.close()
            with pytest.raises(RelayError, match="closed"):
                await receive
            assert alice._receiver.done() and alice._heartbeat.done()
            assert not alice._pending and alice.socket.closed and alice.context.closed
            await alice.close()  # Idempotent.
            with pytest.raises(RelayError, match="closed"):
                await alice.receive()

    asyncio.run(check())
