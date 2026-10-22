import asyncio

import pytest

from nodalwire.client.python.envelope import Envelope, decode_envelope, encode_envelope
from nodalwire.client.python.node import Message
from nodalwire.protocol import RelayError

from .protocol_test import admit, data, dispose, fake_router, packet, receipt


def test_request_reply_before_receipt_preserves_unrelated_wrong_matches_and_binary_bytes():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"request\x00", network="red"))
                sent = await packet(router)
                assert sent[5:7] == [b"red", b"beta"]
                envelope = decode_envelope(sent[7])
                assert envelope.kind == "request" and envelope.payload == b"request\x00"
                reply = encode_envelope(Envelope("reply", envelope.id, b"reply\xff"))
                wrong = [
                    (b"ordinary", "red", "beta"),
                    (reply, "blue", "beta"),
                    (reply, "red", "other"),
                    (encode_envelope(Envelope("reply", "b" * 32, b"id")), "red", "beta"),
                    (encode_envelope(Envelope("request", envelope.id, b"kind")), "red", "beta"),
                ]
                for payload, network, sender in wrong:
                    await data(router, address, payload, network=network, sender=sender)
                await data(router, address, reply, network="red")
                assert await asyncio.wait_for(operation, 1) == Message("beta", b"reply\xff", "red")
                # No SEND receipt was provided; response is sufficient and send wait is cleaned.
                assert not node._pending and not node._app_pending
                for payload, network, sender in wrong:
                    assert node.receive_nowait() == Message(sender, payload, network)
                assert node.receive_nowait() is None
            finally:
                await dispose(node)
    asyncio.run(check())


def test_accepted_reply_wins_cancel_before_request_coroutine_resumes():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"x"))
                sent = await packet(router)
                envelope = decode_envelope(sent[7])
                waiter = node._app_pending[envelope.id]
                waiter.future.add_done_callback(lambda _: operation.cancel())
                await data(
                    router, address, encode_envelope(Envelope("reply", envelope.id, b"wins"))
                )
                assert await operation == Message("beta", b"wins")
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("terminal", ["cancel", "timeout", "rejection"])
def test_terminal_before_reply_leaves_late_reply_readable(terminal):
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"x", timeout=0.08))
                sent = await packet(router)
                envelope = decode_envelope(sent[7])
                if terminal == "cancel":
                    operation.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await operation
                elif terminal == "timeout":
                    from nodalwire import ReceiptTimeout
                    with pytest.raises(ReceiptTimeout, match="uncertain"):
                        await operation
                else:
                    from nodalwire.protocol import ERROR
                    await receipt(router, sent, b"not_member", command=ERROR)
                    with pytest.raises(RelayError, match="not_member"):
                        await operation
                late = encode_envelope(Envelope("reply", envelope.id, b"late"))
                await data(router, address, late)
                assert (await asyncio.wait_for(node.receive(), 1)).payload == late
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


def test_reply_uses_incoming_network_and_rejects_nonrequests():
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                incoming = Message(
                    "beta", encode_envelope(Envelope("request", "c" * 32, b"x")), "red"
                )
                operation = asyncio.create_task(node.reply(incoming, b"answer\x00"))
                sent = await packet(router)
                assert sent[5:7] == [b"red", b"beta"]
                assert decode_envelope(sent[7]) == Envelope("reply", "c" * 32, b"answer\x00")
                await receipt(router, sent)
                await operation
                with pytest.raises(ValueError, match="not a request"):
                    await node.reply(Message("beta", b"ordinary"), b"x")
            finally:
                await dispose(node)
    asyncio.run(check())


def test_request_cap_and_full_ordinary_inbox_backpressure_remain_bounded():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint, inbox_size=1, max_pending=1)
            try:
                operation = asyncio.create_task(node.request("beta", b"x", timeout=0.08))
                sent = await packet(router)
                envelope = decode_envelope(sent[7])
                with pytest.raises(RelayError, match="pending_full"):
                    await node.request("beta", b"another")
                await data(router, address, b"one")
                await data(router, address, b"two")
                reply = encode_envelope(Envelope("reply", envelope.id, b"backpressured"))
                await data(router, address, reply)
                from nodalwire import ReceiptTimeout
                with pytest.raises(ReceiptTimeout):
                    await operation
                assert (await node.receive()).payload == b"one"
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"two"
                assert (await asyncio.wait_for(node.receive(), 1)).payload == reply
            finally:
                await dispose(node)
    asyncio.run(check())
