import asyncio

import pytest

from nodalwire import AdminClient, AdminError, Message, RelayError
from nodalwire.config import NetworkConfig
from nodalwire.credentials import make_verifier

from .helpers import TEST_ADMIN_TOKEN, running_relay


def test_open_defaults_other_open_explicit_join_multiple_membership_and_no_fallback():
    async def check():
        async with running_relay(networks={"red": NetworkConfig(), "blue": NetworkConfig()}) as h:
            alice, bob = await h.node("alice"), await h.node("bob")
            identity = await alice.send("bob", b"auto")
            assert await bob.receive() == Message(
                id=identity, sender="alice", network="default", payload=b"auto"
            )
            with pytest.raises(RelayError, match="not_member"):
                await alice.send("bob", b"no implicit open join", network="red")
            assert (await alice.join("red")).changed
            assert not (await alice.join("red")).changed
            with pytest.raises(RelayError, match="destination_not_member"):
                await alice.send("bob", b"both required", network="red")
            await bob.join("red")
            await alice.join("blue")
            await alice.send("bob", b"red", network="red")
            assert (await bob.receive()).network == "red"
            assert (await alice.leave("default")).changed
            assert not (await alice.leave("default")).changed
            with pytest.raises(RelayError, match="not_member"):
                await alice.send("bob", b"must not fall back to shared red")
            await alice.send("bob", b"still red", network="red")
            assert (await bob.receive()).payload == b"still red"
            await alice.join("default")
            await alice.send("bob", b"default again")
            assert (await bob.receive()).network == "default"
    asyncio.run(check())


def test_protected_default_allows_zero_memberships_then_explicit_join():
    async def check():
        policy = NetworkConfig(join_verifier=make_verifier("default-join!"))
        async with running_relay(networks={"default": policy, "open": NetworkConfig()}) as h:
            alice, bob = await h.node("alice"), await h.node("bob")
            with pytest.raises(RelayError, match="not_member"):
                await alice.send("bob", b"zero memberships")
            for credential in (None, "bad!", TEST_ADMIN_TOKEN):
                with pytest.raises(RelayError, match="join_denied"):
                    await alice.join("default", credential)
            await alice.join("default", "default-join!")
            await bob.join("default", "default-join!")
            await alice.send("bob", b"joined")
            assert (await bob.receive()).network == "default"
            await alice.join("open")
            await bob.join("open")
            await alice.leave("default")
            with pytest.raises(RelayError, match="not_member"):
                await alice.send("bob", b"must still select default")
            await alice.send("bob", b"explicit", network="open")
            assert (await bob.receive()).network == "open"
    asyncio.run(check())


def test_admin_policy_rotation_future_joins_removal_and_accepted_data_cutoff():
    async def check():
        async with running_relay(networks={"red": NetworkConfig()}) as h:
            alice, bob = await h.node("alice"), await h.node("bob")
            await alice.join("red")
            await bob.join("red")
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token=TEST_ADMIN_TOKEN
            ) as admin:
                first = await admin.call("network.update", {
                    "network": "red", "protected": True, "credential": "first-join!",
                }, expected_revision=0)
                assert first.revision == 1
                # Accepted members stay; only future joins now require credential.
                await alice.send("bob", b"existing", network="red")
                assert (await bob.receive()).payload == b"existing"
                carol = await h.node("carol")
                with pytest.raises(RelayError, match="join_denied"):
                    await carol.join("red")
                await carol.join("red", "first-join!")
                await admin.call("network.rotate", {"network": "red", "credential": "second-join!"},
                                 expected_revision=1)
                # Repeating JOIN rechecks policy, but failure does not evict accepted member.
                with pytest.raises(RelayError, match="join_denied"):
                    await alice.join("red", "first-join!")
                await alice.send("bob", b"accepted before removal", network="red")
                removed = await admin.call("member.remove", {"network": "red", "name": "alice"},
                                           expected_revision=2)
                assert removed.revision == 2 and removed.result["changed"]
                assert removed.result["ephemeral"] is True
                # Native-accepted data isn't recalled by membership removal.
                assert (await bob.receive()).payload == b"accepted before removal"
                with pytest.raises(RelayError, match="not_member"):
                    await alice.send("bob", b"after cutoff", network="red")
                with pytest.raises(RelayError, match="join_denied"):
                    await alice.join("red", "first-join!")
                await alice.join("red", "second-join!")
                members = await admin.call("member.list", {"network": "red"})
                assert members.result["members"] == ["alice", "bob", "carol"]
                await admin.call("network.delete", {"network": "red"}, expected_revision=2)
                with pytest.raises(RelayError, match="network_not_found"):
                    await alice.send("bob", b"deleted", network="red")
                await admin.call("network.create", {"network": "red"}, expected_revision=3)
                with pytest.raises(RelayError, match="not_member"):
                    await alice.send("bob", b"recreated not joined", network="red")
    asyncio.run(check())


def test_admin_network_credentials_are_independent_and_config_redacted():
    async def check():
        async with running_relay(networks={
            "red": NetworkConfig(join_verifier=make_verifier("red-join!")),
        }) as h:
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token="red-join!"
            ) as wrong:
                with pytest.raises(AdminError, match="unauthorized"):
                    await wrong.call("config.get")
            alice = await h.node("alice")
            with pytest.raises(RelayError, match="join_denied"):
                await alice.join("red", TEST_ADMIN_TOKEN)
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token=TEST_ADMIN_TOKEN
            ) as admin:
                config = (await admin.call("config.get")).result
                assert config["networks"]["red"] == {"protected": True}
                text = str(config)
                for secret in ("red-join!", TEST_ADMIN_TOKEN, "scrypt-v1", "join_verifier"):
                    assert secret not in text
                with pytest.raises(AdminError, match="reserved_network"):
                    await admin.call("network.delete", {"network": "default"}, expected_revision=0)
                assert (await admin.call("config.get")).revision == 0
                await admin.call("network.create", {"network": "new"}, expected_revision=0)
                with pytest.raises(AdminError, match="revision_conflict"):
                    await admin.call("network.delete", {"network": "new"}, expected_revision=0)
    asyncio.run(check())


def test_real_python_request_reply_on_selected_network_with_unrelated_data():
    async def check():
        async with running_relay(networks={"red": NetworkConfig()}) as h:
            alice, bob = await h.node("alice"), await h.node("bob")
            await alice.join("red")
            await bob.join("red")
            request = asyncio.create_task(alice.request("bob", bytes(range(256)), network="red"))
            incoming = await asyncio.wait_for(bob.receive(), 1)
            unrelated_id = await bob.send("alice", b"unrelated", network="red")
            reply_id = await bob.reply(incoming, b"response\x00\xff")
            assert reply_id != incoming.id
            assert await request == Message(
                id=reply_id, sender="bob", network="red", payload=b"response\x00\xff",
                reply_to=incoming.id,
            )
            assert await alice.receive() == Message(
                id=unrelated_id, sender="bob", network="red", payload=b"unrelated"
            )
    asyncio.run(check())
