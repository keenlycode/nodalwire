"""NWM3 core behavior over real owned sockets, independent of SDK migration."""

import asyncio
import json
from contextlib import asynccontextmanager
from pathlib import Path

import pytest
import zmq
import zmq.asyncio

from nodalwire.admin import AdminClient
from nodalwire.config import NetworkConfig
from nodalwire.protocol import ADMIN_VERSION, JOIN, VERSION

from .helpers import TEST_ADMIN_TOKEN, raw_node, raw_request, running_relay

WIRE = json.loads((Path(__file__).resolve().parents[1] / "fixtures/nwm3/wire.json").read_text())
CID = b"f" * 32


def decode(frames):
    return [frame["ascii"].encode("ascii") if "ascii" in frame else bytes.fromhex(frame["hex"])
            for frame in frames]


def bind_tokens(frames, tokens):
    packet = decode(frames)
    if len(packet) > 2:
        packet[2] = tokens.get(packet[2], packet[2])
    return packet


async def receive(socket):
    async with asyncio.timeout(1):
        return await socket.recv_multipart()


@asynccontextmanager
async def raw_pair(**options):
    options.setdefault("max_payload_bytes", WIRE["context"]["max_payload_bytes"])
    options.setdefault("networks", {"red": NetworkConfig()})
    async with running_relay(**options) as harness:
        async with raw_node(harness.endpoint, "alpha") as alpha:
            async with raw_node(harness.endpoint, "beta") as beta:
                for socket, token in (alpha, beta):
                    result = await raw_request(socket, JOIN, token, b"red", b"")
                    assert result[1] == b"OK"
                peers = {"alpha": alpha, "beta": beta}
                tokens = {registration["token"].encode("ascii"): peers[registration["name"]][1]
                          for registration in WIRE["context"]["registrations"]}
                yield harness, peers, tokens


async def barrier(socket, token):
    """FIFO control receipt proves the preceding same-peer packet was processed."""
    await socket.send_multipart([VERSION, JOIN, token, CID, b"default", b""])
    assert await receive(socket) == [VERSION, b"OK", token, CID, b"default", b"0"]


@pytest.mark.parametrize("route", WIRE["routes"], ids=lambda item: item["name"])
def test_shared_golden_routes_preserve_native_metadata_and_payload(route):
    async def check():
        async with raw_pair() as (_, peers, tokens):
            source = peers[route["source"]][0]
            target = peers[route["destination"]][0]
            await source.send_multipart(bind_tokens(route["send"], tokens))
            assert await receive(source) == bind_tokens(route["receipt"], tokens)
            assert await receive(target) == bind_tokens(route["data"], tokens)
    asyncio.run(check())


@pytest.mark.parametrize("case", WIRE["relay_rejections"], ids=lambda item: item["name"])
def test_shared_golden_rejections_have_no_routing_side_effect(case):
    async def check():
        async with raw_pair() as (_, peers, tokens):
            source, token = peers["alpha"]
            target = peers["beta"][0]
            await source.send_multipart(bind_tokens(case["send"], tokens))
            if case["action"] == "error":
                assert await receive(source) == bind_tokens(case["response"], tokens)
            await barrier(source, token)
            assert not await target.poll(10)
    asyncio.run(check())


def test_duplicate_ids_and_reply_references_do_not_create_broker_state():
    async def check():
        async with raw_pair() as (harness, peers, _):
            source, token = peers["alpha"]
            target, target_token = peers["beta"]
            identity = b"1" * 32
            # Even equal id/reply_to is legal at the relay; fresh IDs are a client rule.
            for reference in (b"", identity, identity):
                packet = [VERSION, b"SEND", token, identity, b"default", b"beta",
                          reference, b"mutation"]
                await source.send_multipart(packet)
                assert await receive(source) == [VERSION, b"OK", token, identity]
                assert await receive(target) == [VERSION, b"DATA", target_token, identity,
                                                 b"default", b"alpha", reference, b"mutation"]
            assert set(harness.relay._names) == {"alpha", "beta"}
            assert not await source.poll(10) and not await target.poll(10)
    asyncio.run(check())


@pytest.mark.parametrize("old_version", [b"AR2", b"AR1", b"AR3", b"NWM3\x00"])
def test_wrong_version_hello_cannot_register_or_trigger_fallback(old_version):
    async def check():
        async with running_relay() as harness:
            context = zmq.asyncio.Context()
            socket = context.socket(zmq.DEALER)
            socket.setsockopt(zmq.LINGER, 0)
            socket.connect(harness.endpoint)
            try:
                await socket.send_multipart([old_version, b"HELLO", b"old", b"alpha"])
                # A subsequent NWM3 HELLO from the same socket/name must succeed.
                await socket.send_multipart([VERSION, b"HELLO", CID, b"alpha"])
                reply = await receive(socket)
                assert reply[:4] == [VERSION, b"OK", b"", CID]
                assert len(reply) == 8
                assert set(harness.relay._names) == {"alpha"}
                assert not await socket.poll(10)
            finally:
                socket.close(linger=0)
                context.term()
    asyncio.run(check())


@pytest.mark.parametrize("changes, code", [
    ({"network": b"bad network"}, b"invalid_network"),
    ({"destination": b"bad destination"}, b"invalid_destination"),
    ({"network": b"missing"}, b"network_not_found"),
    ({"destination": b"missing"}, b"destination_unavailable"),
])
def test_existing_routing_validation_still_rejects_without_data(changes, code):
    async def check():
        async with raw_pair() as (_, peers, _):
            source, token = peers["alpha"]
            packet = [VERSION, b"SEND", token, b"1" * 32,
                      changes.get("network", b"default"),
                      changes.get("destination", b"beta"), b"", b"payload"]
            await source.send_multipart(packet)
            assert await receive(source) == [VERSION, b"ERROR", token, b"1" * 32, code]
            assert not await peers["beta"][0].poll(10)
    asyncio.run(check())


def test_metadata_validation_precedes_names_and_payload_and_arity_precedes_ids():
    async def check():
        async with raw_pair() as (_, peers, _):
            source, token = peers["alpha"]
            identity = b"1" * 31
            packet = [VERSION, b"SEND", token, identity, b"bad network", b"bad dest",
                      b"bad reply", b"x" * 257]
            for replacement, expected in [
                (packet, b"invalid_id"),
                (packet[:3] + [b"1" * 32] + packet[4:], b"invalid_reply_to"),
                (packet + [b"extra"], b"invalid_command"),
            ]:
                await source.send_multipart(replacement)
                assert await receive(source) == [VERSION, b"ERROR", token, replacement[3], expected]
            assert not await peers["beta"][0].poll(10)
    asyncio.run(check())


def test_existing_deny_policy_and_membership_checks_are_unchanged():
    async def check():
        async with raw_pair(deny=(("alpha", "beta"),)) as (_, peers, _):
            source, token = peers["alpha"]
            packet = [VERSION, b"SEND", token, b"1" * 32, b"red", b"beta", b"", b"x"]
            await source.send_multipart(packet)
            assert (await receive(source))[-1] == b"route_denied"
            target, target_token = peers["beta"]
            assert (await raw_request(target, b"LEAVE", target_token, b"red"))[1] == b"OK"
            await source.send_multipart(packet)
            assert (await receive(source))[-1] == b"destination_not_member"
            assert (await raw_request(source, b"LEAVE", token, b"red"))[1] == b"OK"
            await source.send_multipart(packet)
            assert (await receive(source))[-1] == b"not_member"
            assert not await target.poll(10)
    asyncio.run(check())


def test_queue_acceptance_does_not_wait_for_consumption_and_close_keeps_queued_data():
    async def check():
        async with raw_pair() as (_, peers, _):
            source, token = peers["alpha"]
            target, target_token = peers["beta"]
            packet = [VERSION, b"SEND", token, b"1" * 32, b"default", b"beta", b"", b"x"]
            await source.send_multipart(packet)
            # No target application receive has run when acceptance arrives.
            assert await receive(source) == [VERSION, b"OK", token, b"1" * 32]
            assert (await raw_request(source, b"CLOSE", token))[1] == b"OK"
            assert await receive(target) == [VERSION, b"DATA", target_token, b"1" * 32,
                                             b"default", b"alpha", b"", b"x"]
            await source.send_multipart(packet)
            assert (await receive(source))[-1] == b"not_registered"
    asyncio.run(check())


def test_lease_expiry_cannot_be_revived_by_stale_heartbeat():
    async def check():
        async with raw_pair(lease_seconds=0.1) as (_, peers, _):
            source, token = peers["alpha"]
            await asyncio.sleep(0.15)  # Exercise real lease expiry, not readiness polling.
            await source.send_multipart([VERSION, b"HEARTBEAT", token])
            await source.send_multipart([VERSION, b"JOIN", token, CID, b"default", b""])
            assert await receive(source) == [VERSION, b"ERROR", token, CID, b"not_registered"]
    asyncio.run(check())


def test_na1_config_and_ephemeral_membership_operations_with_native_messaging():
    async def check():
        assert ADMIN_VERSION == b"NA1"
        async with raw_pair() as (harness, peers, _):
            admin = await AdminClient.connect(harness.relay.admin_endpoint, token=TEST_ADMIN_TOKEN)
            try:
                config = await admin.call("config.get")
                assert config.revision == 0
                members = await admin.call("member.list", {"network": "red"})
                assert members.result == {"network": "red", "members": ["alpha", "beta"]}
                removed = await admin.call("member.remove", {"network": "red", "name": "beta"},
                                           expected_revision=0)
                assert removed.revision == 0 and removed.result["ephemeral"] is True
                source, token = peers["alpha"]
                packet = [VERSION, b"SEND", token, b"1" * 32, b"red", b"beta", b"", b"x"]
                await source.send_multipart(packet)
                assert (await receive(source))[-1] == b"destination_not_member"
                created = await admin.call(
                    "network.create", {"network": "new"}, expected_revision=0,
                )
                assert created.revision == 1
                deleted = await admin.call(
                    "network.delete", {"network": "red"}, expected_revision=1,
                )
                assert deleted.revision == 2
                await source.send_multipart(packet)
                assert (await receive(source))[-1] == b"network_not_found"
            finally:
                await admin.close()
    asyncio.run(check())
