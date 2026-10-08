"""Bounded real Python relay/client to built Node client verification."""

import asyncio
import os
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT / "src"))

from nodalwire import Node, Relay, RelayConfig  # noqa: E402


async def main():
    relay = Relay(RelayConfig(
        endpoint="tcp://127.0.0.1:*", lease_seconds=0.3,
        max_payload_bytes=1024, deny=(("js-node", "py-denied"),),
    ))
    endpoint = await relay.start()
    service = asyncio.create_task(relay.run())
    echo = await Node.connect("py-echo", endpoint)
    seen = []

    async def reflect():
        while True:
            message = await echo.receive()
            assert message.sender == "js-node", message.sender
            seen.append(message.payload.hex())
            await echo.send(message.sender, message.payload)

    reflector = asyncio.create_task(reflect())
    child = None
    try:
        child = await asyncio.create_subprocess_exec(
            "node", str(Path(__file__).with_name("interop.mjs")), endpoint,
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        result = await asyncio.wait_for(child.wait(), 25)
        assert result == 0, result
        assert "" in seen and bytes(range(256)).hex() in seen, seen
        print(f"PASS Python↔Node: {len(seen)} messages, actual sender, arbitrary/empty bytes")
    finally:
        if child is not None and child.returncode is None:
            child.kill()
            await child.wait()
        reflector.cancel()
        await asyncio.gather(reflector, return_exceptions=True)
        await echo.close()
        service.cancel()
        await asyncio.gather(service, return_exceptions=True)
        await relay.close()
        print("PASS Python-owned relay/client cleanup")


asyncio.run(main())
