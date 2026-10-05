import asyncio

import pytest

from nodalwire import Node, RelayError
from nodalwire.protocol import CLOSE, SEND

from .helpers import raw_node, raw_request, running_relay


def test_opaque_bytes_bidirectional_multiple_nodes_and_empty_payload():
    async def check():
        async with running_relay() as h:
            alice, bob, carol = [await h.node(name) for name in ("alice", "bob", "carol")]
            payload = bytes(range(256)) + b"\x00\xffopaque\x00"
            await alice.send("bob", payload)
            message = await asyncio.wait_for(bob.receive(), 1)
            assert (message.sender, message.payload) == ("alice", payload)
            await bob.send("alice", b"reply\x00")
            assert (await alice.receive()).sender == "bob"
            await carol.send("alice", b"")
            assert (await alice.receive()).payload == b""
            await alice.send("alice", b"loopback")
            assert (await alice.receive()).payload == b"loopback"

    asyncio.run(check())


def test_receipt_is_queue_acceptance_without_application_read():
    async def check():
        async with running_relay() as h:
            sender = await h.node("sender")
            async with raw_node(h.endpoint, "unread"):
                # Destination never reads again after its actual HELLO reply.
                await sender.send("unread", b"not remotely consumed", timeout=1)

    asyncio.run(check())


def test_absent_destination_invalid_payload_and_local_size_limit():
    async def check():
        async with running_relay(max_payload_bytes=8) as h:
            source = await h.node("source")
            with pytest.raises(RelayError, match="destination_unavailable"):
                await source.send("absent", b"x")
            with pytest.raises(RelayError, match="payload_too_large"):
                await source.send("absent", b"123456789")
            with pytest.raises(TypeError):
                await source.send("absent", "not bytes")
            with pytest.raises(ValueError):
                await source.send("@bad", b"x")
            async with raw_node(h.endpoint, "raw") as (socket, token):
                reply = await raw_request(socket, SEND, token, b"source", b"123456789")
                assert reply[-1] == b"payload_too_large"
                reply = await raw_request(socket, SEND, token, b"@bad", b"x")
                assert reply[-1] == b"invalid_destination"

    asyncio.run(check())


def test_directional_network_and_exact_denies_win_default_allow():
    async def check():
        async with running_relay(
            networks={"red": ("alice", "carol"), "blue": ("bob",)},
            deny=(("@red", "@blue"), ("bob", "carol")),
        ) as h:
            alice, bob, carol = [await h.node(name) for name in ("alice", "bob", "carol")]
            with pytest.raises(RelayError, match="route_denied"):
                await alice.send("bob", b"forbidden")
            with pytest.raises(RelayError, match="route_denied"):
                await carol.send("bob", b"forbidden")
            with pytest.raises(RelayError, match="route_denied"):
                await bob.send("carol", b"forbidden")
            await bob.send("alice", b"reverse permitted")
            assert (await alice.receive()).payload == b"reverse permitted"
            await alice.send("carol", b"same network permitted")
            assert (await carol.receive()).sender == "alice"

    asyncio.run(check())


def test_wildcard_deny_and_admission_allowlist():
    async def check():
        async with running_relay(allowed_names=("alice", "bob"), deny=(("*", "bob"),)) as h:
            alice, bob = [await h.node(name) for name in ("alice", "bob")]
            with pytest.raises(RelayError, match="admission_denied"):
                await Node.connect("outsider", h.endpoint)
            with pytest.raises(RelayError, match="route_denied"):
                await alice.send("bob", b"blocked")
            await bob.send("alice", b"permitted")
            assert (await alice.receive()).sender == "bob"

    asyncio.run(check())


def test_duplicate_active_name_then_clean_release_and_new_incarnation():
    async def check():
        async with running_relay() as h:
            original = await h.node("alice")
            old_token = original._token
            with pytest.raises(RelayError, match="duplicate_name"):
                await Node.connect("alice", h.endpoint)
            await original.close()
            replacement = await h.node("alice")
            assert replacement._token != old_token
            await replacement.send("alice", b"fresh")
            assert (await replacement.receive()).sender == "alice"
            with pytest.raises(RelayError, match="closed"):
                await original.send("alice", b"old")

    asyncio.run(check())


def test_sender_is_registration_not_application_payload_or_claimed_frame():
    async def check():
        async with running_relay() as h:
            bob = await h.node("bob")
            async with raw_node(h.endpoint, "alice") as (socket, token):
                claimed = b'{"sender":"admin"}\x00'
                reply = await raw_request(socket, SEND, token, b"bob", claimed)
                assert reply[1] == b"OK"
                message = await bob.receive()
                assert message.sender == "alice" and message.payload == claimed
                # Extra claimed-sender frame is not a valid transport message.
                reply = await raw_request(socket, SEND, token, b"bob", b"admin", b"x")
                assert reply[-1] == b"invalid_command"
                await raw_request(socket, CLOSE, token)

    asyncio.run(check())
