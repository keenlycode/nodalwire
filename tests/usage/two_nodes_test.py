"""Public API usage: an embedded relay and two nodes exchanging opaque bytes."""

import asyncio
from contextlib import suppress

from nodalwire import Node, Relay, RelayConfig


def test_two_nodes_exchange_bytes():
    async def application():
        # Select an available loopback port; no separately running service is needed.
        async with Relay(RelayConfig(endpoint="tcp://127.0.0.1:*")) as relay:
            endpoint = relay.endpoint
            service = asyncio.create_task(relay.run())
            try:
                async with (
                    await Node.connect("alice", endpoint) as alice,
                    await Node.connect("bob", endpoint) as bob,
                ):
                    await alice.send("bob", b"hello\x00")
                    incoming = await asyncio.wait_for(bob.receive(), timeout=2)
                    assert incoming.sender == "alice"
                    assert incoming.payload == b"hello\x00"

                    # Reply to the sender supplied by the relay, not a payload field.
                    await bob.send(incoming.sender, b"reply\xff")
                    reply = await asyncio.wait_for(alice.receive(), timeout=2)
                    assert reply.sender == "bob"
                    assert reply.payload == b"reply\xff"
            finally:
                # Stop and await the service before its context closes the relay.
                service.cancel()
                with suppress(asyncio.CancelledError):
                    await service

    asyncio.run(application())
