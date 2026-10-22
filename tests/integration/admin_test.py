import asyncio
import json

import pytest

from nodalwire.admin import AdminClient, AdminError, AdminReceipt
from nodalwire.protocol import ADMIN_VERSION, ERROR, OK, ReceiptTimeout, RelayError

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
