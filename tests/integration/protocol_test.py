"""Python client behavior against a real owned ROUTER, independent of store work."""

import asyncio
import contextlib
import json
from contextlib import asynccontextmanager

import pytest
import zmq
import zmq.asyncio

from nodalwire.client.python.node import MembershipReceipt, Message, Node
from nodalwire.protocol import (
    CLOSE,
    DATA,
    ERROR,
    HELLO,
    JOIN,
    LEAVE,
    OK,
    SEND,
    VERSION,
    ReceiptTimeout,
    RelayError,
)

TOKEN = b"a" * 32


@asynccontextmanager
async def fake_router():
    context = zmq.asyncio.Context()
    router = context.socket(zmq.ROUTER)
    router.setsockopt(zmq.LINGER, 0)
    router.bind("tcp://127.0.0.1:*")
    endpoint = router.getsockopt(zmq.LAST_ENDPOINT).decode()
    try:
        yield router, endpoint
    finally:
        router.close(linger=0)
        context.term()


async def packet(router):
    return await asyncio.wait_for(router.recv_multipart(), 1)


async def admit(router, endpoint, *, memberships=b'[]', name="alpha", token=TOKEN,
                limit=b"1048576", **options):
    connect = asyncio.create_task(Node.connect(name, endpoint, **options))
    hello = await packet(router)
    assert hello[1:3] == [VERSION, HELLO]
    assert hello[4] == name.encode("ascii")
    await router.send_multipart([
        hello[0], VERSION, OK, b"", hello[3], token, b"10.0", limit, memberships,
    ])
    return await connect, hello[0]


async def dispose(node):
    with contextlib.suppress(RelayError, ReceiptTimeout):
        await node.close(timeout=0.01)
    assert node.socket.closed and node.context.closed


async def data(router, address, payload, *, network="default", sender="beta", token=TOKEN,
               identity="d" * 32, reply_to=None):
    await router.send_multipart([
        address, VERSION, DATA, token, identity.encode("ascii"),
        network.encode("ascii"), sender.encode("ascii"),
        b"" if reply_to is None else reply_to.encode("ascii"), payload,
    ])


async def receipt(router, request, *extra, command=OK):
    await router.send_multipart([request[0], VERSION, command, request[3], request[4], *extra])


def test_zero_memberships_and_exact_network_control_frames():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.join("red", "credential!"))
                request = await packet(router)
                assert request[1:4] == [VERSION, JOIN, TOKEN]
                assert request[5:] == [b"red", b"credential!"]
                await receipt(router, request, b"red", b"1")
                assert await operation == MembershipReceipt("red", True, True)
                operation = asyncio.create_task(node.leave("red"))
                request = await packet(router)
                assert request[2] == LEAVE and request[5:] == [b"red"]
                await receipt(router, request, b"red", b"0")
                assert await operation == MembershipReceipt("red", False, False)
                operation = asyncio.create_task(node.send("beta", b"bytes", network="red"))
                request = await packet(router)
                assert request[2] == SEND and request[5:] == [b"red", b"beta", b"", b"bytes"]
                await receipt(router, request)
                assert await operation == request[4].decode("ascii")
                await data(router, address, bytes(range(256)) * 32, network="red")
                message = await asyncio.wait_for(node.receive(), 1)
                assert message == Message(
                    id="d" * 32, sender="beta", network="red", payload=bytes(range(256)) * 32
                )
                operation = asyncio.create_task(node.send("beta", b"default"))
                request = await packet(router)
                assert request[5] == b"default"  # Not last joined red.
                await receipt(router, request)
                await operation
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("extra", [(b"red", b"2"), (b"blue", b"1"), (), (b"red", b"1", b"x")])
def test_malformed_matching_membership_success_immediately_rejects(extra):
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.join("red"))
                request = await packet(router)
                await receipt(router, request, *extra)
                with pytest.raises(RelayError, match="invalid_receipt"):
                    await operation
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("extras", [
    (TOKEN, b"nan", b"1000", b"[]"), (TOKEN, b"10", b"0", b"[]"),
    (TOKEN, b"10", b"1000", b'["red"]'), (b"bad", b"10", b"1000", b"[]"),
    (TOKEN, b"10", b"1000", b'null'), (TOKEN, b"10", b"1000"),
    (TOKEN, b"1_0", b"1000", b"[]"), (TOKEN, b"+10", b"1000", b"[]"),
    (TOKEN, b"1e1", b"1000", b"[]"), (TOKEN, b"010", b"1000", b"[]"),
    (TOKEN, b" 10", b"1000", b"[]"), (TOKEN, b"10\n", b"1000", b"[]"),
    (TOKEN, b"10", b"1000", b"[ ]"), (TOKEN, b"10", b"1000", b'[ "default" ]'),
])
def test_invalid_hello_cannot_install_partial_admission(extras):
    async def check():
        async with fake_router() as (router, endpoint):
            connect = asyncio.create_task(Node.connect("alpha", endpoint))
            hello = await packet(router)
            await router.send_multipart([hello[0], VERSION, OK, b"", hello[3], *extras])
            with pytest.raises(RelayError, match="invalid_receipt"):
                await connect
    asyncio.run(check())


def test_stale_incarnation_and_invalid_ascii_data_are_not_admitted():
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                await data(router, address, b"stale", token=b"b" * 32)
                await router.send_multipart([
                    address, VERSION, DATA, TOKEN, b"d" * 32, b"default", b"\xe1lice", b"", b"bad",
                ])
                await data(router, address, b"good")
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"good"
                assert node.receive_nowait() is None
                for token in ("", "bad\n", "é"):
                    with pytest.raises(ValueError, match="credential"):
                        await node.join("red", token)
            finally:
                await dispose(node)
                assert node.receive_nowait() is None
    asyncio.run(check())


def test_unsupported_old_wire_is_never_used_as_fallback():
    async def check():
        async with fake_router() as (router, endpoint):
            connect = asyncio.create_task(Node.connect("alpha", endpoint, timeout=0.05))
            hello = await packet(router)
            assert hello[1] == b"NWM3"
            await router.send_multipart([
                hello[0], b"AR2", OK, b"", hello[3], TOKEN, b"10", b"1024",
            ])
            with pytest.raises(ReceiptTimeout):
                await connect
            assert not await router.poll(0)
    asyncio.run(check())


def test_typed_errors_and_clean_release_shape():
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            send = asyncio.create_task(node.send("beta", b"x"))
            request = await packet(router)
            await receipt(router, request, b"not_member", command=ERROR)
            with pytest.raises(RelayError, match="not_member"):
                await send
            close = asyncio.create_task(node.close())
            request = await packet(router)
            assert request[2] == CLOSE and len(request) == 5
            await receipt(router, request)
            await close
            assert node.socket.closed and node.context.closed
    asyncio.run(check())


def test_strict_control_json_rejects_duplicate_nonfinite_and_invalid_utf8():
    from nodalwire.protocol import json_object
    for raw in (b'{"x":1,"x":2}', b'{"x":Infinity}', b'{"x":1e999}', b'[]', b'\xff'):
        with pytest.raises(ValueError):
            json_object(raw)
    assert json_object(json.dumps({"x": [1, 2]}).encode()) == {"x": [1, 2]}
