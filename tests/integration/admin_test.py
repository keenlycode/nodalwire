import asyncio
import json

import pytest

from nodalwire.admin import AdminClient, AdminError, AdminReceipt
from nodalwire.config import RelayConfig, load_config
from nodalwire.config_store import ConfigStore
from nodalwire.protocol import ADMIN_VERSION, ERROR, OK, ReceiptTimeout, RelayError
from nodalwire.server import Relay

from .helpers import TEST_ADMIN_TOKEN, TEST_ADMIN_VERIFIER, running_relay
from .protocol_test import fake_router, packet


def test_admin_transport_is_separate_bounded_and_typed():
    async def check():
        async with fake_router() as (router, endpoint):
            client = await AdminClient.connect(endpoint, token="fake-admin!")
            try:
                call = asyncio.create_task(client.call("network.create", {"network": "red"},
                                                       expected_revision=0))
                sent = await packet(router)
                assert sent[1] == ADMIN_VERSION and sent[3] == b"fake-admin!"
                assert json.loads(sent[4]) == {
                    "op": "network.create", "args": {"network": "red"}, "expected_revision": 0,
                }
                with pytest.raises(RelayError, match="pending_full"):
                    await client.call("config.get")
                await router.send_multipart([
                    sent[0], ADMIN_VERSION, sent[2], OK,
                    b'{"revision":1,"result":{"network":"red","protected":false}}',
                ])
                assert await call == AdminReceipt(1, {"network": "red", "protected": False})
                call = asyncio.create_task(client.call("admin.rotate", {"credential": "new!"},
                                                       expected_revision=1))
                sent = await packet(router)
                await router.send_multipart([
                    sent[0], ADMIN_VERSION, sent[2], ERROR,
                    b'{"revision":2,"code":"persistence_indeterminate","outcome":"indeterminate"}',
                ])
                with pytest.raises(AdminError) as caught:
                    await call
                assert caught.value.code == "persistence_indeterminate"
                assert caught.value.outcome == "indeterminate" and caught.value.revision == 2
                assert "fake-admin" not in str(caught.value) and "new!" not in repr(caught.value)
            finally:
                await client.close()
                await client.close()
                assert client.socket.closed and client.context.closed
    asyncio.run(check())


@pytest.mark.parametrize("reply", [
    b'{"revision":true,"result":{}}', b'{"revision":0,"result":[]}',
    b'{"revision":0,"result":{},"extra":1}', b'{"revision":0,"revision":1,"result":{}}',
    b'{"revision":0,"result":{"x":NaN}}', b'\xff',
])
def test_malformed_admin_success_never_succeeds(reply):
    async def check():
        async with fake_router() as (router, endpoint):
            client = await AdminClient.connect(endpoint, token="test!")
            try:
                call = asyncio.create_task(client.call("config.get"))
                sent = await packet(router)
                await router.send_multipart([sent[0], ADMIN_VERSION, sent[2], OK, reply])
                with pytest.raises(RelayError, match="invalid_receipt"):
                    await call
            finally:
                await client.close()
    asyncio.run(check())


def test_admin_timeout_is_uncertain_no_retry_and_late_receipt_not_reused():
    async def check():
        async with fake_router() as (router, endpoint):
            client = await AdminClient.connect(endpoint, token="test!")
            try:
                call = asyncio.create_task(client.call("network.delete", {"network": "red"},
                                                       expected_revision=0, timeout=0.03))
                sent = await packet(router)
                with pytest.raises(ReceiptTimeout, match="uncertain"):
                    await call
                assert not await router.poll(0)  # No automatic retry.
                await router.send_multipart([
                    sent[0], ADMIN_VERSION, sent[2], OK, b'{"revision":1,"result":{}}',
                ])
                call = asyncio.create_task(client.call("config.get"))
                new = await packet(router)
                assert new[2] != sent[2]
                await router.send_multipart([
                    new[0], ADMIN_VERSION, new[2], OK, b'{"revision":2,"result":{}}',
                ])
                assert (await call).revision == 2
            finally:
                await client.close()
    asyncio.run(check())


def test_admin_client_validates_before_send_and_cancellation_does_not_retry():
    async def check():
        async with fake_router() as (router, endpoint):
            client = await AdminClient.connect(endpoint, token="test!")
            try:
                for op, revision in (("network.create", None), ("network.create", True),
                                     ("config.get", 0)):
                    with pytest.raises(ValueError):
                        await client.call(op, expected_revision=revision)
                call = asyncio.create_task(client.call("config.get"))
                await packet(router)
                call.cancel()
                with pytest.raises(asyncio.CancelledError):
                    await call
                assert not client._pending and not await router.poll(0)
            finally:
                await client.close()
    asyncio.run(check())


def _file_store(tmp_path):
    path = tmp_path / "relay.toml"
    path.write_text(f'''config_version = 2
admin_verifier = "{TEST_ADMIN_VERIFIER}"
endpoint = "tcp://127.0.0.1:*"
admin_endpoint = "tcp://127.0.0.1:*"
[networks.red]
''')
    return path, ConfigStore(load_config(path), path, environ={})


def test_live_persistence_failure_and_indeterminate_deletion_side_effects(tmp_path, monkeypatch):
    import os
    import stat

    import nodalwire.config_store as module

    async def check():
        path, store = _file_store(tmp_path)
        async with running_relay(store=store) as h:
            alice, bob = await h.node("alice"), await h.node("bob")
            await alice.join("red")
            await bob.join("red")
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token=TEST_ADMIN_TOKEN
            ) as admin:
                original_bytes = path.read_bytes()

                def fail_replace(*args):
                    raise OSError("private-os-detail")

                with monkeypatch.context() as patch:
                    patch.setattr(module.os, "replace", fail_replace)
                    with pytest.raises(AdminError) as error:
                        await admin.call("network.delete", {"network": "red"}, expected_revision=0)
                    assert error.value.code == "persistence_failed"
                    assert error.value.outcome == "no_effect" and error.value.revision == 0
                assert path.read_bytes() == original_bytes
                await alice.send("bob", b"membership unchanged", network="red")
                assert (await bob.receive()).payload == b"membership unchanged"
                original_fsync = module.os.fsync

                def fail_parent(fd):
                    if stat.S_ISDIR(os.fstat(fd).st_mode):
                        raise OSError("private-os-detail")
                    return original_fsync(fd)

                with monkeypatch.context() as patch:
                    patch.setattr(module.os, "fsync", fail_parent)
                    with pytest.raises(AdminError) as error:
                        await admin.call("network.delete", {"network": "red"}, expected_revision=0)
                    assert error.value.code == "persistence_indeterminate"
                    assert error.value.outcome == "indeterminate" and error.value.revision == 1
                    assert "private-os-detail" not in str(error.value)
                assert load_config(path) == store.snapshot()
                assert "red" not in (await admin.call("config.get")).result["networks"]
                # Recreate makes membership side effects observable: old memberships
                # must NOT survive even when original deletion reported indeterminate.
                await admin.call("network.create", {"network": "red"}, expected_revision=1)
                with pytest.raises(RelayError, match="not_member"):
                    await alice.send("bob", b"old membership must be gone", network="red")
                assert list(path.parent.iterdir()) == [path]
        restarted = ConfigStore(load_config(path), path, environ={})
        async with running_relay(store=restarted) as h:
            alice, bob = await h.node("alice"), await h.node("bob")
            with pytest.raises(RelayError, match="not_member"):
                await alice.send("bob", b"ephemeral across restart", network="red")
            await alice.join("red")
            await bob.join("red")
            await alice.send("bob", b"fresh join", network="red")
            assert (await bob.receive()).payload == b"fresh join"
    asyncio.run(check())


def test_config_managed_admin_rotation_survives_restart_and_env_mode_rejects(tmp_path):
    async def check():
        path, store = _file_store(tmp_path)
        async with running_relay(store=store) as h:
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token=TEST_ADMIN_TOKEN
            ) as old:
                result = await old.call("admin.rotate", {"credential": "new-admin-token!"},
                                        expected_revision=0)
                assert result.revision == 1
                with pytest.raises(AdminError, match="unauthorized"):
                    await old.call("config.get")
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token="new-admin-token!"
            ) as new:
                assert (await new.call("config.get")).result["admin_source"] == "config"
        assert "new-admin-token!" not in path.read_text()
        restarted = ConfigStore(load_config(path), path, environ={})
        assert restarted.authenticate_admin("new-admin-token!")
        overridden = ConfigStore(load_config(path), path,
                                 environ={"NODALWIRE_ADMIN_TOKEN": "env-admin-token!"})
        before = path.read_bytes()
        async with running_relay(store=overridden) as h:
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token="env-admin-token!"
            ) as admin:
                with pytest.raises(AdminError, match="environment_managed"):
                    await admin.call("admin.rotate", {"credential": "forbidden!"},
                                     expected_revision=1)
                result = await admin.call("config.get")
                assert result.result["admin_source"] == "environment"
                assert "env-admin-token!" not in str(result)
        assert path.read_bytes() == before
    asyncio.run(check())


def test_admin_strict_request_shapes_and_opaque_peer_payloads():
    async def check():
        async with running_relay() as h:
            alice, bob = await h.node("alice"), await h.node("bob")
            wire_like = b'NA1\\x00{"op":"network.delete","args":{"network":"default"}}'
            await alice.send("bob", wire_like)
            assert (await bob.receive()).payload == wire_like
            async with await AdminClient.connect(
                h.relay.admin_endpoint, token=TEST_ADMIN_TOKEN
            ) as admin:
                for op, args, code in (
                    ("network.get", {"network": "default", "extra": 1}, "invalid_request"),
                    ("network.update", {"network": "default", "protected": "yes"},
                     "invalid_policy"),
                    ("network.update", {"network": "default", "protected": True},
                     "credential_required"),
                    ("network.get", {"network": "missing"}, "network_not_found"),
                ):
                    kwargs = {"expected_revision": 0} if op == "network.update" else {}
                    with pytest.raises(AdminError) as error:
                        await admin.call(op, args, **kwargs)
                    assert error.value.code == code and error.value.revision == 0
    asyncio.run(check())


def test_startup_requires_admin_before_resources_and_partial_bind_failure_closes(monkeypatch):
    import zmq
    import zmq.asyncio

    monkeypatch.delenv("NODALWIRE_ADMIN_TOKEN", raising=False)
    with pytest.raises(ValueError, match="credential required"):
        Relay(RelayConfig())

    async def check():
        context = zmq.asyncio.Context()
        occupied = context.socket(zmq.ROUTER)
        occupied.setsockopt(zmq.LINGER, 0)
        occupied.bind("tcp://127.0.0.1:*")
        endpoint = occupied.getsockopt(zmq.LAST_ENDPOINT).decode()
        config = RelayConfig(endpoint="tcp://127.0.0.1:*", admin_endpoint=endpoint,
                             admin_verifier=TEST_ADMIN_VERIFIER)
        relay = Relay(store=ConfigStore(config, environ={}))
        try:
            with pytest.raises(zmq.ZMQError):
                await relay.start()
            assert relay.socket.closed and relay.context.closed
        finally:
            await relay.close()
            occupied.close(linger=0)
            context.term()
    asyncio.run(check())
