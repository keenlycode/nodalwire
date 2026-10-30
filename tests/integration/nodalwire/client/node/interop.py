"""Bounded owned NWM3 relay/Python clients to built or installed Node client.

Default mode uses this checkout, or NODALWIRE_PYTHON_SOURCE selects reviewed src/.
NODALWIRE_PYTHON_INSTALLED=1 instead requires an isolated external environment;
package_smoke.py --python-artifact stages these fixtures outside the checkout.
"""

import asyncio
import os
import sys
from pathlib import Path

INSTALLED = os.environ.get("NODALWIRE_PYTHON_INSTALLED") == "1"
SOURCE_SETTING = os.environ.get("NODALWIRE_PYTHON_SOURCE")
if not INSTALLED:
    if not SOURCE_SETTING:
        raise RuntimeError("Set NODALWIRE_PYTHON_SOURCE to the exact reviewed NWM3 source tree")
    SOURCE = Path(SOURCE_SETTING).resolve()
    sys.path.insert(0, str(SOURCE))

import nodalwire  # noqa: E402
from nodalwire import AdminClient, Node, Relay, RelayConfig  # noqa: E402
from nodalwire.config import NetworkConfig  # noqa: E402
from nodalwire.config_store import ConfigStore  # noqa: E402
from nodalwire.credentials import make_verifier  # noqa: E402
from nodalwire.protocol import VERSION as PYTHON_VERSION  # noqa: E402

assert PYTHON_VERSION == b"NWM3", f"Interop requires NWM3 Python source, got {PYTHON_VERSION!r}"


def validate_installed_paths(module, prefix, runtime, paths, checkout, cwd):
    """Allow only the interpreter's own stdlib beneath a task-local checkout."""
    module, prefix, runtime, checkout, cwd = (
        Path(value).resolve() for value in (module, prefix, runtime, checkout, cwd)
    )
    source = checkout / "src"
    assert not prefix.is_relative_to(checkout), "Consumer venv is in checkout"
    assert module.is_relative_to(prefix), f"Not a venv package: {module}"
    assert not cwd.is_relative_to(checkout), "Consumer is in checkout"
    assert runtime != checkout and not runtime.is_relative_to(source), "Invalid runtime root"
    for value in paths:
        if not value:
            continue
        path = Path(value).resolve()
        assert not path.is_relative_to(source), "Repository source import path leaked"
        if path.is_relative_to(checkout):
            assert runtime.is_relative_to(checkout) and path.is_relative_to(runtime), (
                "Checkout path outside managed interpreter leaked")


if INSTALLED:
    from importlib.metadata import distribution

    SOURCE = Path(nodalwire.__file__).resolve().parent
    prefix = Path(sys.prefix).resolve()
    metadata = distribution("nodalwire")
    assert sys.flags.isolated, "Installed acceptance requires Python -I"
    assert Path(metadata.locate_file("")).resolve().is_relative_to(prefix)
    forbidden = Path(os.environ["NODALWIRE_FORBIDDEN_SOURCE"]).resolve()
    validate_installed_paths(SOURCE, prefix, sys.base_prefix, sys.path, forbidden, Path.cwd())
    assert metadata.version == os.environ["NODALWIRE_EXPECTED_VERSION"]
    print(f"PASS installed Python provenance: version={metadata.version}; "
          f"module={SOURCE}; prefix={prefix}; sys.path={sys.path}", flush=True)


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
                if message.payload.startswith(b"node-request-fixture:"):
                    # Request is ordinary raw DATA; its reply uses fresh native IDs.
                    await echo.send(message.sender, b"unrelated", network=message.network)
                    await echo.reply(message, message.payload[len(b"node-request-fixture:"):])
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
        print(f"PASS Python↔Node NWM3 ({'protected' if protected_default else 'open'} default): "
              f"{len(seen)} messages; python={SOURCE}; "
              f"mode={'installed' if INSTALLED else 'source'}")
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


if __name__ == "__main__":
    asyncio.run(main())
