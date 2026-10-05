"""Run after starting the local relay; bytes and reply meanings belong to the app."""

import asyncio

from nodalwire import Node


async def main() -> None:
    alice = await Node.connect("alice")
    try:
        bob = await Node.connect("bob")
        try:
            await alice.send("bob", b"hello\x00")
            incoming = await bob.receive()
            print(incoming.sender, repr(incoming.payload))
            await bob.send(incoming.sender, b"reply\xff")
            print(await alice.receive())
        finally:
            await bob.close()
    finally:
        await alice.close()


if __name__ == "__main__":
    asyncio.run(main())
