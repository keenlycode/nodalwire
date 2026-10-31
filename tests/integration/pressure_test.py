import asyncio
import contextlib
import secrets
from contextlib import asynccontextmanager

import pytest
import zmq
import zmq.asyncio

from nodalwire import Node, ReceiptTimeout, RelayError
from nodalwire.protocol import CLOSE, HELLO, OK, SEND, VERSION

from .helpers import raw_node, running_relay


def test_full_native_destination_errors_and_other_route_progresses_without_drops():
    async def check():
        payload_size = 512 * 1024
        async with running_relay(send_hwm=1, max_payload_bytes=payload_size) as h:
            sender = await h.node("sender")
            other = await h.node("other")
            async with raw_node(h.endpoint, "busy", receive_hwm=1) as (socket, token):
                accepted = []
                for number in range(100):
                    payload = number.to_bytes(4, "big") + b"x" * (payload_size - 4)
                    try:
                        await sender.send("busy", payload, timeout=1)
                    except RelayError as exc:
                        assert exc.code == "destination_full"
                        break
                    accepted.append(number)
                else:
                    pytest.fail("native bounded destination never reported pressure")
                assert accepted  # Not a disconnected/missing destination fixture.
                await asyncio.wait_for(sender.send("other", b"unrelated"), 0.5)
                assert (await other.receive()).payload == b"unrelated"
                # Every acknowledged message, no extra full-queue message, is readable.
                received = []
                for _ in accepted:
                    packet = await asyncio.wait_for(socket.recv_multipart(), 2)
                    assert packet[:3] == [VERSION, b"DATA", token]
                    assert packet[4:7] == [b"default", b"sender", b""]
                    assert len(packet[7]) == payload_size
                    received.append(int.from_bytes(packet[7][:4], "big"))
                assert received == accepted
                assert not await socket.poll(timeout=30)

    asyncio.run(check())


@asynccontextmanager
async def silent_receipt_peer():
    """A real ROUTER admits once, then records effects without responding to requests."""
    context = zmq.asyncio.Context()
    socket = context.socket(zmq.ROUTER)
    socket.setsockopt(zmq.LINGER, 0)
    socket.bind("tcp://127.0.0.1:*")
    endpoint = socket.getsockopt(zmq.LAST_ENDPOINT).decode()
    captured = asyncio.Queue()
    token = secrets.token_hex(16).encode()

    async def serve():
        first = await socket.recv_multipart()
        assert first[1:3] == [VERSION, HELLO]
        await socket.send_multipart(
            [first[0], VERSION, OK, b"", first[3], token, b"10", b"1048576", b'["default"]']
        )
        while True:
            packet = await socket.recv_multipart()
            if packet[2] in (SEND, CLOSE):
                await captured.put(packet)

    task = asyncio.create_task(serve())
    try:
        yield endpoint, captured
    finally:
        task.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await task
        socket.close(linger=0)
        context.term()


def test_receipt_timeout_uncertainty_never_replays_and_pending_map_is_bounded():
    async def check():
        async with silent_receipt_peer() as (endpoint, captured):
            node = await Node.connect("alice", endpoint, max_pending=1)
            try:
                first = asyncio.create_task(node.send("bob", b"effect", timeout=0.15))
                packet = await asyncio.wait_for(captured.get(), 1)
                assert packet[-1] == b"effect"  # Effect reached native peer before timeout.
                with pytest.raises(RelayError, match="pending_full"):
                    await node.send("bob", b"not sent")
                with pytest.raises(ReceiptTimeout, match="uncertain"):
                    await first
                assert not node._pending
                # No automatic replay is emitted while an explicit CLOSE traverses same pipe.
                with pytest.raises(ReceiptTimeout):
                    await node.close(timeout=0.1)
                close = await captured.get()
                assert close[2] == CLOSE and captured.empty()
                assert node.socket.closed and node.context.closed and node._receiver.done()
                assert node._heartbeat.done() and not node._pending
            finally:
                await node.close()

    asyncio.run(check())


def test_close_interrupts_pending_send_with_lifecycle_error_after_native_effect():
    async def check():
        async with silent_receipt_peer() as (endpoint, captured):
            node = await Node.connect("alice", endpoint)
            request = asyncio.create_task(node.send("bob", b"effect before close"))
            assert (await captured.get())[-1] == b"effect before close"
            with pytest.raises(ReceiptTimeout):
                await node.close(timeout=0.05)
            # closed is NOT a Router no-effect rejection for an interrupted request.
            with pytest.raises(RelayError, match="closed"):
                await request
            assert node.socket.closed and node.context.closed and not node._pending

    asyncio.run(check())


def test_cancelled_send_and_cancelled_close_always_release_resources():
    async def check():
        async with silent_receipt_peer() as (endpoint, captured):
            node = await Node.connect("alice", endpoint)
            request = asyncio.create_task(node.send("bob", b"uncertain cancelled send"))
            await captured.get()
            request.cancel()
            with pytest.raises(asyncio.CancelledError):
                await request
            assert not node._pending
            close = asyncio.create_task(node.close())
            assert (await captured.get())[2] == CLOSE
            close.cancel()
            with pytest.raises(asyncio.CancelledError):
                await close
            assert node.socket.closed and node.context.closed
            assert node._heartbeat.done() and node._receiver.done() and not node._pending

    asyncio.run(check())


def test_cancellation_during_cleanup_task_join_still_closes_native_resources():
    async def check():
        async with running_relay() as h:
            node = await h.node("alice")
            # Gate an owned child task's cancellation, making the cleanup-join
            # boundary deterministic instead of hoping a scheduling race is hit.
            node._heartbeat.cancel()
            await asyncio.gather(node._heartbeat, return_exceptions=True)
            ready, joining, release = asyncio.Event(), asyncio.Event(), asyncio.Event()

            async def gated_heartbeat():
                ready.set()
                try:
                    await asyncio.Future()
                except asyncio.CancelledError:
                    joining.set()
                    await release.wait()

            node._heartbeat = asyncio.create_task(gated_heartbeat())
            await ready.wait()
            closing = asyncio.create_task(node.close())
            repeated = None
            try:
                await asyncio.wait_for(joining.wait(), 1)
                assert node._closed.is_set() and not node._cleanup_done.is_set()
                closing.cancel()
                await asyncio.sleep(0)
                closing.cancel()  # Repeated caller cancellation must not cancel cleanup.
                repeated = asyncio.create_task(node.close())
                await asyncio.sleep(0)
                assert not closing.done() and not repeated.done()
                release.set()
                with pytest.raises(asyncio.CancelledError):
                    await asyncio.wait_for(closing, 1)
                await asyncio.wait_for(repeated, 1)
                assert node.socket.closed and node.context.closed
                assert node._receiver.done() and node._heartbeat.done()
                assert node._cleanup_task.done() and not node._pending
                assert node._cleanup_done.is_set()
            finally:
                release.set()
                await asyncio.gather(closing, *([repeated] if repeated else []),
                                     return_exceptions=True)
                await node.close()

    asyncio.run(check())


def test_full_client_inbox_bounds_storage_and_failed_close_cleanup():
    async def check():
        async with running_relay(lease_seconds=0.15) as h:
            alice = await h.node("alice", inbox_size=1)
            sender = await h.node("sender")
            for payload in (b"one", b"two"):
                await sender.send("alice", payload)
            # Sending from alice ensures its receipt is behind already queued DATA.
            with pytest.raises(ReceiptTimeout):
                await alice.send("sender", b"effect despite unread inbox", timeout=0.3)
            assert (await sender.receive()).payload == b"effect despite unread inbox"
            assert alice._inbox.qsize() == 1 and not alice._pending
            with pytest.raises(RelayError, match="duplicate_name"):
                await Node.connect("alice", h.endpoint)  # Heartbeat survives > one lease.
            with pytest.raises(ReceiptTimeout):
                await alice.close(timeout=0.1)
            assert alice.socket.closed and alice.context.closed
            assert alice._receiver.done() and alice._heartbeat.done()
            # Router processed CLOSE even though alice could not read its receipt.
            replacement = await h.node("alice")
            await replacement.send("sender", b"fresh")
            assert (await sender.receive()).payload == b"fresh"

    asyncio.run(check())
