"""Native Python API checks consuming the frozen, shared NWM3 wire fixtures."""

import asyncio
import dataclasses
import json
import re
from pathlib import Path
from unittest.mock import patch

import pytest
import zmq

from nodalwire import Message, ReceiptTimeout, RelayError
from nodalwire.protocol import ERROR

from .protocol_test import admit, data, dispose, fake_router, packet, receipt

FIXTURES = json.loads((Path(__file__).parents[1] / "fixtures/nwm3/wire.json").read_text())


def frames(encoded):
    return [item["ascii"].encode("ascii") if "ascii" in item else bytes.fromhex(item["hex"])
            for item in encoded]


@pytest.mark.parametrize("route", FIXTURES["routes"], ids=lambda route: route["name"])
def test_shared_route_fixtures_send_data_receipt_and_message(route):
    async def check():
        registrations = {item["name"]: item for item in FIXTURES["context"]["registrations"]}
        source = registrations[route["source"]]
        target = registrations[route["destination"]]
        async with fake_router() as (router, endpoint):
            sender, _ = await admit(router, endpoint, name=source["name"],
                                    token=source["token"].encode(), limit=b"256")
            receiver, address = await admit(router, endpoint, name=target["name"],
                                            token=target["token"].encode(), limit=b"256")
            try:
                expected = frames(route["send"])
                operation = asyncio.create_task(sender.send(
                    route["destination"], expected[-1], network=expected[4].decode(),
                    reply_to=expected[6].decode() or None,
                ))
                sent = await packet(router)
                generated_id = sent[4]
                assert re.fullmatch(rb"[0-9a-f]{32}", generated_id)
                expected[3] = generated_id
                assert sent[1:] == expected
                assert not operation.done()  # Never resolve before acceptance.
                accepted = frames(route["receipt"])
                accepted[3] = generated_id
                await router.send_multipart([sent[0], *accepted])
                assert await operation == generated_id.decode()
                await router.send_multipart([address, *frames(route["data"])])
                message = await asyncio.wait_for(receiver.receive(), 1)
                expected_message = route["message"]
                assert dataclasses.asdict(message) == {
                    "id": expected_message["id"], "sender": expected_message["sender"],
                    "network": expected_message["network"],
                    "payload": bytes.fromhex(expected_message["payload_hex"]),
                    "reply_to": expected_message["reply_to"],
                }
            finally:
                await dispose(sender)
                await dispose(receiver)
    asyncio.run(check())


@pytest.mark.parametrize("case", FIXTURES["client_discard"], ids=lambda case: case["name"])
def test_shared_malformed_data_fixtures_are_dropped(case):
    async def check():
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint, name="beta", token=b"b" * 32,
                                        limit=b"256")
            try:
                await router.send_multipart([address, *frames(case["data"])])
                await data(router, address, b"valid sentinel", token=b"b" * 32)
                assert (await asyncio.wait_for(node.receive(), 1)).payload == b"valid sentinel"
                assert node.receive_nowait() is None
            finally:
                await dispose(node)
    asyncio.run(check())


def test_shared_correlation_fixtures_match_all_three_native_metadata_fields():
    async def check():
        correlation = FIXTURES["correlation"]
        async with fake_router() as (router, endpoint):
            node, address = await admit(router, endpoint)
            try:
                with patch("nodalwire.client.python.node.secrets.token_hex",
                           return_value=correlation["waiter"]["id"]):
                    operation = asyncio.create_task(node.request("beta", b"native"))
                    sent = await packet(router)
                assert sent[4].decode() == correlation["waiter"]["id"]
                # Wrong sender, network, reference or absent reference remain inbox data.
                ordinary = [case for case in correlation["cases"] if case["owner"] == "inbox"]
                matching = next(case for case in correlation["cases"] if case["owner"] == "request")
                for case in ordinary:
                    await router.send_multipart([address, *frames(case["data"])])
                await router.send_multipart([address, *frames(matching["data"])])
                reply = await asyncio.wait_for(operation, 1)
                assert reply.id == "2" * 32 and reply.reply_to == "1" * 32
                assert reply.payload == b"reply"
                for case in ordinary:
                    message = node.receive_nowait()
                    wire = frames(case["data"])
                    assert message.sender == wire[5].decode()
                    assert message.network == wire[4].decode()
                    assert message.reply_to == (wire[6].decode() or None)
                await router.send_multipart([address, *frames(matching["data"])])
                assert await asyncio.wait_for(node.receive(), 1) == reply
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("reply_to", ["", "a" * 31, "A" * 32, "g" * 32, "a" * 31 + "\n",
                                     "é" * 32, b"a" * 32, 0, False])
def test_invalid_local_reply_metadata_rejected_before_write(reply_to):
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                with pytest.raises(ValueError, match="reply_to"):
                    await node.send("beta", b"x", reply_to=reply_to)
                assert not node._pending and not await router.poll(0)
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("field,value", [
    ("id", "bad"), ("id", "A" * 32), ("reply_to", ""), ("reply_to", "bad"),
    ("sender", "bad name"), ("network", "bad name"), ("payload", bytearray(b"x")),
])
def test_reply_validates_incoming_message_before_write(field, value):
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                incoming = Message(id="c" * 32, sender="beta", network="default", payload=b"x")
                incoming = dataclasses.replace(incoming, **{field: value})
                with pytest.raises((ValueError, TypeError)):
                    await node.reply(incoming, b"answer")
                assert not node._pending and not await router.poll(0)
            finally:
                await dispose(node)
    asyncio.run(check())


@pytest.mark.parametrize("code", ["invalid_id", "invalid_reply_to"])
def test_new_relay_errors_are_recognized_and_preserve_typed_codes(code):
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.send("beta", b"x"))
                sent = await packet(router)
                await receipt(router, sent, code.encode(), command=ERROR)
                with pytest.raises(RelayError) as caught:
                    await operation
                assert caught.value.code == code
            finally:
                await dispose(node)
    asyncio.run(check())


def test_fresh_ids_avoid_outstanding_control_app_and_reference_ids():
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                first = asyncio.create_task(node.send("beta", b"one"))
                first_wire = await packet(router)
                reference = "c" * 32
                # A live request reserves its ID before even scheduling its SEND.
                request = asyncio.create_task(node.request("beta", b"request"))
                request_wire = await packet(router)
                sequence = [first_wire[4].decode(), request_wire[4].decode(), reference, "f" * 32]
                with patch("nodalwire.client.python.node.secrets.token_hex", side_effect=sequence):
                    second = asyncio.create_task(node.send("beta", b"two", reply_to=reference))
                    second_wire = await packet(router)
                assert second_wire[4] == b"f" * 32
                assert second_wire[7] == reference.encode()
                await receipt(router, first_wire)
                await receipt(router, second_wire)
                assert await first == first_wire[4].decode()
                assert await second == "f" * 32
                request.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await request
                assert not node._pending and not node._app_pending
            finally:
                await dispose(node)
    asyncio.run(check())


def test_request_waiter_exists_at_native_write_and_local_failure_wins_synchronously():
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            original = node.socket.send_multipart
            observed = []

            def blocked(body, **options):
                identity = body[3].decode()
                observed.append(identity)
                assert identity in node._app_pending
                raise zmq.Again()

            try:
                node.socket.send_multipart = blocked
                with pytest.raises(RelayError, match="local_queue_full"):
                    await node.request("beta", b"x")
                assert len(observed) == 1
                assert not node._pending and not node._app_pending
                assert not await router.poll(0)
            finally:
                node.socket.send_multipart = original
                await dispose(node)
    asyncio.run(check())


def test_request_validation_is_prewrite_and_no_public_id_injection():
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint, limit=b"4")
            try:
                for payload in ("text", bytearray(b"x"), memoryview(b"x")):
                    with pytest.raises(TypeError):
                        await node.request("beta", payload)
                with pytest.raises(RelayError, match="payload_too_large"):
                    await node.request("beta", b"12345")
                for timeout in (0, -1, float("nan"), float("inf"), True):
                    with pytest.raises(ValueError):
                        await node.request("beta", b"x", timeout=timeout)
                with pytest.raises(TypeError):
                    await node.send("beta", b"x", id="a" * 32)
                with pytest.raises(TypeError):
                    await node.request("beta", b"x", reply_to="a" * 32)
                assert not node._pending and not node._app_pending
                assert not await router.poll(0)
            finally:
                await dispose(node)
    asyncio.run(check())


def test_send_timeout_never_returns_a_premature_generated_id():
    async def check():
        async with fake_router() as (router, endpoint):
            node, _ = await admit(router, endpoint)
            try:
                operation = asyncio.create_task(node.send("beta", b"x", timeout=0.04))
                await packet(router)
                assert not operation.done()
                with pytest.raises(ReceiptTimeout):
                    await operation
                assert not node._pending
            finally:
                await dispose(node)
    asyncio.run(check())
