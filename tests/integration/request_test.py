import asyncio

import pytest

from nodalwire import Message, ReceiptTimeout, RelayError
from nodalwire.protocol import ERROR

from .protocol_test import admit, data, dispose, fake_router, packet, receipt


def test_request_reply_before_receipt_preserves_wrong_matches_and_opaque_bytes():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"request\x00", network="red"))
                sent = await packet(router)
                identity = sent[4].decode("ascii")
                assert sent[5:] == [b"red", b"beta", b"", b"request\x00"]
                wrong = [
                    (b"ordinary", "red", "beta", None),
                    (b"reply", "blue", "beta", identity),
                    (b"reply", "red", "other", identity),
                    (b"wrong id", "red", "beta", "b" * 32),
                    (b'NWR1\n{"v":1,"kind":"reply"}', "red", "beta", None),
                ]
                for payload, network, sender, reply_to in wrong:
                    await data(router, address, payload, network=network, sender=sender,
                               reply_to=reply_to)
                await data(router, address, b"reply\xff", network="red", reply_to=identity)
                assert await asyncio.wait_for(operation, 1) == Message(
                    id="d" * 32, sender="beta", network="red", payload=b"reply\xff",
                    reply_to=identity,
                )
                # No SEND OK: matching native DATA is sufficient.
                assert not node._pending and not node._app_pending
                for payload, network, sender, reply_to in wrong:
                    assert node.receive_nowait() == Message(
                        id="d" * 32, sender=sender, network=network, payload=payload,
                        reply_to=reply_to,
                    )
                await data(router, address, b"duplicate", network="red", reply_to=identity)
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"duplicate"
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("malformed_success", [False, True])
def test_reader_rejection_before_adjacent_reply_wins_and_late_reply_is_ordinary(malformed_success):
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"x"))
                sent = await packet(router)
                identity = sent[4].decode("ascii")
                if malformed_success:
                    await receipt(router, sent, b"unexpected extra success frame")
                    code = "invalid_receipt"
                else:
                    await receipt(router, sent, b"not_member", command=ERROR)
                    code = "not_member"
                await data(router, address, b"late", reply_to=identity)
                with pytest.raises(RelayError, match=code):
                    await asyncio.wait_for(operation, 1)
                late = await asyncio.wait_for(node.receive(), 1)
                assert late.payload == b"late" and late.reply_to == identity
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


def test_reader_reply_before_adjacent_send_rejection_keeps_owned_result():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"x"))
                sent = await packet(router)
                identity = sent[4].decode("ascii")
                await data(router, address, b"first", reply_to=identity)
                await receipt(router, sent, b"not_member", command=ERROR)
                result = await asyncio.wait_for(operation, 1)
                assert result.payload == b"first" and result.reply_to == identity
                assert node.receive_nowait() is None
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("cancel_count", [1, 2])
@pytest.mark.parametrize("before_resume", [False, True])
def test_owned_reply_survives_cancellation_before_resume_and_during_join(
    cancel_count, before_resume,
):
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"x"))
                sent = await packet(router)
                identity = sent[4].decode("ascii")
                loop = asyncio.get_running_loop()
                remaining = cancel_count

                def cancel():
                    nonlocal remaining
                    operation.cancel()
                    remaining -= 1
                    if remaining:
                        loop.call_soon(cancel)

                node._app_pending[identity].future.add_done_callback(
                    lambda _: cancel() if before_resume else loop.call_soon(cancel)
                )
                await data(router, address, b"owned", reply_to=identity)
                result = await operation
                assert result.payload == b"owned" and result.reply_to == identity
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("cancel_count", [1, 2])
def test_owned_ordinary_data_survives_cancellation_during_receive_join(cancel_count):
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                loop = asyncio.get_running_loop()
                owner = loop.create_future()
                original_get = node._inbox.get

                async def observed_get():
                    owner.set_result(asyncio.current_task())
                    return await original_get()

                node._inbox.get = observed_get
                operation = asyncio.create_task(node.receive())
                getter = await owner
                remaining = cancel_count

                def cancel():
                    nonlocal remaining
                    operation.cancel()
                    remaining -= 1
                    if remaining:
                        loop.call_soon(cancel)

                getter.add_done_callback(lambda _: loop.call_soon(cancel))
                await data(router, address, b"ordinary-owned")
                assert (await operation).payload == b"ordinary-owned"
                assert node.receive_nowait() is None
            finally:
                await dispose(node)
    asyncio.run(check())


def test_receive_cancellation_before_ownership_leaves_following_data_readable():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                started = asyncio.Event()
                original_get = node._inbox.get

                async def observed_get():
                    started.set()
                    return await original_get()

                node._inbox.get = observed_get
                operation = asyncio.create_task(node.receive())
                await started.wait()
                operation.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await operation
                await data(router, address, b"after cancel")
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"after cancel"
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("terminal", ["cancel", "timeout", "rejection", "close"])
def test_terminal_before_reply_leaves_late_reply_readable(terminal):
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.request("beta", b"x", timeout=0.08))
                sent = await packet(router)
                identity = sent[4].decode("ascii")
                if terminal == "cancel":
                    operation.cancel()
                    with pytest.raises(asyncio.CancelledError):
                        await operation
                elif terminal == "timeout":
                    with pytest.raises(ReceiptTimeout, match="uncertain"):
                        await operation
                elif terminal == "close":
                    await node._cleanup()
                    with pytest.raises(RelayError, match="closed"):
                        await operation
                    assert not node._pending and not node._app_pending
                    return
                else:
                    await receipt(router, sent, b"not_member", command=ERROR)
                    with pytest.raises(RelayError, match="not_member"):
                        await operation
                await data(router, address, b"late", reply_to=identity)
                late = await asyncio.wait_for(node.receive(), 1)
                assert late.payload == b"late" and late.reply_to == identity
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


def test_reply_uses_native_metadata_and_accepts_prior_reply():
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                incoming = Message(
                    id="c" * 32, sender="beta", network="red", payload=b"x", reply_to="b" * 32
                )
                operation = asyncio.create_task(node.reply(incoming, b"answer\x00"))
                sent = await packet(router)
                assert sent[5:] == [b"red", b"beta", b"c" * 32, b"answer\x00"]
                assert sent[4] != b"c" * 32
                assert not operation.done()
                await receipt(router, sent)
                assert await operation == sent[4].decode("ascii")
                with pytest.raises(ValueError, match="incoming id"):
                    await node.reply(
                        Message(id="bad", sender="beta", network="red", payload=b"ordinary"), b"x"
                    )
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
                identity = sent[4].decode("ascii")
                with pytest.raises(RelayError, match="pending_full"):
                    await node.request("beta", b"another")
                await data(router, address, b"one")
                await data(router, address, b"two")
                await data(router, address, b"backpressured", reply_to=identity)
                with pytest.raises(ReceiptTimeout):
                    await operation
                assert (await node.receive()).payload == b"one"
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"two"
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"backpressured"
            finally:
                await dispose(node)
    asyncio.run(check())


def test_one_deadline_includes_send_acceptance_and_reply_wait():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                loop = asyncio.get_running_loop()
                started = loop.time()
                operation = asyncio.create_task(node.request("beta", b"x", timeout=0.15))
                sent = await packet(router)
                await asyncio.sleep(0.09)
                await receipt(router, sent)
                with pytest.raises(ReceiptTimeout):
                    await operation
                assert loop.time() - started < 0.22  # Not a second full reply deadline.
                await data(router, address, b"late", reply_to=sent[4].decode("ascii"))
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"late"
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())
