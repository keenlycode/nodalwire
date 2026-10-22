"""Bounded owned AR2 relay/Python clients to built or installed Node client.

NODALWIRE_PYTHON_SOURCE may select an explicitly reviewed source tree's src/;
otherwise use this checkout. No modification/copy of the selected Python code.
"""

import asyncio
import os
from pathlib import Path
import sys

SOURCE = Path(os.environ.get(
    "NODALWIRE_PYTHON_SOURCE", str(Path(__file__).resolve().parents[4]),
)).resolve()
sys.path.insert(0, str(SOURCE))

from nodalwire import AdminClient, Node, Relay, RelayConfig  # noqa: E402
from nodalwire.client.python import decode_envelope  # noqa: E402
from nodalwire.config import NetworkConfig  # noqa: E402
from nodalwire.credentials import make_verifier  # noqa: E402
from nodalwire.config_store import ConfigStore  # noqa: E402


async def scenario(protected_default=False):
    config = RelayConfig(
        endpoint="tcp://127.0.0.1:*", admin_endpoint="tcp://127.0.0.1:*",
        lease_seconds=0.3, max_payload_bytes=1024,
        deny=(("js-node", "py-denied"),),
        admin_verifier=make_verifier("fixture-admin-token"),
        networks={
            "default": NetworkConfig(
                join_verifier=make_verifier("fixture-default-token")
                if protected_default else None,
            ),
            "team": NetworkConfig(join_verifier=make_verifier("fixture-team-token")),
            "other": NetworkConfig(),
        },
    )
    # Ignore ambient admin credentials for deterministic owned fixture setup.
    relay = Relay(store=ConfigStore(config, environ={}))
    endpoint = await relay.start()
    service = asyncio.create_task(relay.run())
    echo = None
    denied = None
    admin = None
    reflector = None
    child = None
    seen = []
    try:
        echo = await Node.connect("py-echo", endpoint)
        if not protected_default:
            # Test deny policy against an existing registered destination; a
            # missing destination correctly rejects before policy evaluation.
            denied = await Node.connect("py-denied", endpoint)
        if protected_default:
            await echo.join("default", "fixture-default-token")
        else:
            await echo.join("team", "fixture-team-token")
            await echo.join("other")

        admin = await AdminClient.connect(relay.admin_endpoint, token="fixture-admin-token")

        async def reflect():
            revision = 0
            while True:
                message = await echo.receive()
                assert message.sender == "js-node", message.sender
                seen.append(message.payload.hex())
                envelope = decode_envelope(message.payload, max_bytes=1024)
                if envelope is not None and envelope.kind == "request":
                    # Ordinary unrelated DATA must survive request correlation.
                    await echo.send(message.sender, b"unrelated", network=message.network)
                    await echo.reply(message, envelope.payload)
                elif message.payload == b"rotate-team-fixture":
                    result = await admin.call(
                        "network.rotate", {"network": "team", "credential": "fixture-team-new"},
                        expected_revision=revision,
                    )
                    revision = result.revision
                    # Existing memberships survive rotation: this send still works.
                    await echo.send("js-node", b"rotated-team", network="team")
                elif message.payload == b"remove-team-fixture":
                    # Receipt proves native acceptance before explicit removal;
                    # client must retain this DATA even after removal is effective.
                    await echo.send("js-node", b"accepted-before-remove", network="team")
                    await admin.call(
                        "member.remove", {"network": "team", "name": "js-node"},
                        expected_revision=revision,
                    )
                    await echo.send("js-node", b"removed-team", network="default")
                elif message.payload == b"python-request":
                    response = await echo.request(
                        "js-node", bytes(range(256)), network=message.network,
                    )
                    assert response.network == message.network
                    assert response.sender == "js-node"
                    assert response.payload == bytes(range(256))
                    await echo.send("js-node", b"python-request-ok", network=message.network)
                else:
                    await echo.send(message.sender, message.payload, network=message.network)

        reflector = asyncio.create_task(reflect())
        child = await asyncio.create_subprocess_exec(
            "node", str(Path(__file__).with_name("interop.mjs")), endpoint,
            "protected" if protected_default else "open",
            env={**os.environ, "NODE_NO_WARNINGS": "1"},
        )
        # Watch the service too: a Python fixture error should not look like a
        # mysteriously timed-out child. Each child has its own bounded duration.
        exit_wait = asyncio.create_task(child.wait())
        try:
            done, _ = await asyncio.wait(
                [exit_wait, reflector, service], timeout=25,
                return_when=asyncio.FIRST_COMPLETED,
            )
            if reflector in done:
                await reflector
                raise AssertionError("reflector exited unexpectedly")
            if service in done:
                await service
                raise AssertionError("relay exited unexpectedly")
            if exit_wait not in done:
                raise TimeoutError("Node interop exceeded 25 seconds")
            assert exit_wait.result() == 0, exit_wait.result()
        finally:
            exit_wait.cancel()
            await asyncio.gather(exit_wait, return_exceptions=True)
        if not protected_default:
            assert "" in seen and bytes(range(256)).hex() in seen, seen
        print(f"PASS Python↔Node AR2 ({'protected' if protected_default else 'open'} default): "
              f"{len(seen)} messages; source={SOURCE}")
    finally:
        if child is not None and child.returncode is None:
            child.kill()
            await child.wait()
        if reflector is not None:
            reflector.cancel()
            await asyncio.gather(reflector, return_exceptions=True)
        if echo is not None:
            await echo.close()
        if denied is not None:
            await denied.close()
        if admin is not None:
            await admin.close()
        service.cancel()
        await asyncio.gather(service, return_exceptions=True)
        await relay.close()
        print("PASS Python-owned relay/client/process cleanup")


async def main():
    await scenario()
    await scenario(protected_default=True)


asyncio.run(main())
