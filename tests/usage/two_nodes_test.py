"""Public API usage: an embedded relay and two nodes exchanging opaque bytes."""

import asyncio
from contextlib import suppress

from nodalwire import Node, Relay, RelayConfig


def test_two_nodes_exchange_bytes(monkeypatch):
    # An explicitly supplied administrator credential is required even when all
    # networks are open. Real applications supply their own high-entropy value.
    monkeypatch.setenv("NODALWIRE_ADMIN_TOKEN", "usage-only-administrator-token!")

    async def application():
        # Select an available loopback port; no separately running service is needed.
        config = RelayConfig(endpoint="tcp://127.0.0.1:*", admin_endpoint="tcp://127.0.0.1:*")
        async with Relay(config) as relay:
            endpoint = relay.endpoint
            service = asyncio.create_task(relay.run())
            try:
                async with (
                    await Node.connect("alice", endpoint) as alice,
                    await Node.connect("bob", endpoint) as bob,
                ):
                    accepted_id = await alice.send("bob", b"hello\x00")
                    incoming = await asyncio.wait_for(bob.receive(), timeout=2)
                    assert incoming.id == accepted_id
                    assert incoming.reply_to is None
                    assert incoming.sender == "alice"
                    assert incoming.payload == b"hello\x00"
                    assert incoming.network == "default"

                    # Reply to the sender supplied by the relay, not a payload field.
                    reply_id = await bob.reply(incoming, b"reply\xff")
                    assert reply_id != accepted_id
                    reply = await asyncio.wait_for(alice.receive(), timeout=2)
                    assert reply.id == reply_id and reply.reply_to == accepted_id
                    assert reply.sender == "bob"
                    assert reply.payload == b"reply\xff"
            finally:
                # Stop and await the service before its context closes the relay.
                service.cancel()
                with suppress(asyncio.CancelledError):
                    await service

    asyncio.run(application())
