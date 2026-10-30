"""Run authored guide snippets against owned, ephemeral matching relays.

Extraction locates executable CodeBlock inputs, not maintained prose wording.
Node source is evaluated unchanged in a temporary application using package-name
imports via the built source fixture. This is not installed-artifact acceptance.
No package install, shared build, or coordination relay.
"""

import asyncio
import os
import re
import shutil
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from nodalwire import AdminClient, AdminError, Node, Relay, RelayConfig, RelayError, load_config
from nodalwire.config import NetworkConfig
from nodalwire.credentials import make_verifier

ROOT = Path(__file__).resolve().parents[3]
SOURCE = ROOT / "src/docs-src"
ADMIN_TOKEN = "guides-only-administrator-token!"
JOIN_TOKEN = "guides-only-join-token!"


def snippet(route, name):
    source = (SOURCE / route / "index.html").read_text(encoding="utf-8")
    match = re.search(
        r"\{% set " + re.escape(name) + r" %\}(.*?)\{% endset %\}", source, re.DOTALL,
    )
    assert match is not None, f"missing executable snippet {route}:{name}"
    code = match.group(1)
    assert code.endswith("\n"), "authored copy input must include its final newline"
    return code


def python_example(route, name):
    scope = {"__name__": "guide_example"}
    code = snippet(route, name)
    exec(compile(code, f"{route}/{name}", "exec"), scope)
    return scope


@asynccontextmanager
async def running_example(monkeypatch, *, networks=None):
    monkeypatch.setenv("NODALWIRE_ADMIN_TOKEN", ADMIN_TOKEN)
    config = RelayConfig(
        endpoint="tcp://127.0.0.1:*", admin_endpoint="tcp://127.0.0.1:*",
        networks={} if networks is None else networks,
    )
    async with Relay(config) as relay:
        service = asyncio.create_task(relay.run())
        try:
            async with asyncio.timeout(15):
                yield relay
        finally:
            service.cancel()
            await asyncio.gather(service, return_exceptions=True)
    assert relay.socket.closed and relay.admin_socket.closed and relay.context.closed


@pytest.mark.parametrize("protected", [False, True], ids=["open-team", "protected-default"])
def test_authored_network_examples(monkeypatch, protected):
    if protected:
        function = python_example("guides/networks", "protected_example")["exchange_protected"]
        policies = {"default": NetworkConfig(join_verifier=make_verifier(JOIN_TOKEN))}
    else:
        function = python_example("guides/networks", "open_example")["exchange_open"]
        policies = {"team": NetworkConfig()}

    async def check():
        async with running_example(monkeypatch, networks=policies) as relay:
            async with (
                await Node.connect("guide-alice", relay.endpoint) as alice,
                await Node.connect("guide-bob", relay.endpoint) as bob,
            ):
                if protected:
                    with pytest.raises(RelayError) as failure:
                        await alice.send(bob.name, b"not joined")
                    assert failure.value.code == "not_member"
                    with pytest.raises(RelayError) as failure:
                        await alice.join("default", ADMIN_TOKEN)
                    assert failure.value.code == "join_denied"
                    incoming = await function(alice, bob, JOIN_TOKEN)
                    assert incoming.sender == alice.name
                else:
                    incoming = await function(alice, bob)
                    assert incoming.network == "team"
                    await alice.leave("default")
                    with pytest.raises(RelayError) as failure:
                        await alice.send(bob.name, b"no fallback")
                    assert failure.value.code == "not_member"
                    assert not (await alice.join("team")).changed
                    await alice.send(bob.name, b"still team", network="team")
                    assert (await bob.receive()).payload == b"still team"

    asyncio.run(check())


def test_authored_python_request_reply(monkeypatch):
    function = python_example("guides/request-reply", "python_request")["round_trip"]

    async def check():
        async with running_example(monkeypatch) as relay:
            async with (
                await Node.connect("request-alice", relay.endpoint) as alice,
                await Node.connect("request-bob", relay.endpoint) as bob,
            ):
                response = await function(alice, bob)
                assert response.payload == b"answer\xff"
                assert alice.receive_nowait() is None

    asyncio.run(check())


def test_authored_node_request_reply(monkeypatch, node_application):
    node = shutil.which("node")
    assert node is not None, "Node.js 24 is required; absence is not behavior proof"
    module = ROOT / "src/nodalwire/client/node/dist/index.js"
    assert module.is_file(), "build the reviewed matching SDK before this check"
    code = snippet("guides/request-reply", "node_request")

    async def check():
        async with running_example(monkeypatch) as relay:
            # -e module resolution uses the temporary application's package name.
            # Keep the complete authored module unmodified; append only its caller.
            runner = code + '''
import assert from "node:assert/strict";
import { Node } from "@devcapsule/nodalwire-client";
const alice = await Node.connect("node-request-alice", process.argv[1]);
try {
  const bob = await Node.connect("node-request-bob", process.argv[1]);
  try {
    const response = await roundTrip(alice, bob);
    assert.equal(response.sender, bob.name);
    assert.equal(response.network, "default");
    assert.deepEqual(response.payload, Uint8Array.of(2, 255));
    assert.equal(alice.receiveNowait(), undefined);
  } finally { await bob.close(); }
} finally { await alice.close(); }
'''
            process = await asyncio.create_subprocess_exec(
                node, "--input-type=module", "-e", runner, relay.endpoint, cwd=node_application,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            )
            try:
                stdout, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
                assert process.returncode == 0, stderr.decode(errors="replace")
                assert stdout == b""
            finally:
                if process.returncode is None:
                    process.kill()
                    await process.wait()

    asyncio.run(check())


def test_authored_node_api_fragment(monkeypatch, node_application):
    node = shutil.which("node")
    assert node is not None, "Node.js 24 is required; absence is not behavior proof"
    code = snippet("reference/api", "node_lifecycle")

    async def check():
        async with running_example(monkeypatch) as relay:
            async with await Node.connect("bob", relay.endpoint) as bob:
                async def echo_one():
                    incoming = await asyncio.wait_for(bob.receive(), timeout=5)
                    assert incoming.sender == "alice"
                    assert incoming.network == "default"
                    assert incoming.payload == bytes([0, 255])
                    await bob.send(incoming.sender, incoming.payload, network=incoming.network)

                echo = asyncio.create_task(echo_one())
                process = None
                try:
                    # Exact source, import resolution, and endpoint override from the page.
                    process = await asyncio.create_subprocess_exec(
                        node, "--input-type=module", "-e", code, cwd=node_application,
                        env={**os.environ, "NODALWIRE_ENDPOINT": relay.endpoint},
                        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
                    )
                    _, stderr = await asyncio.wait_for(process.communicate(), timeout=10)
                    assert process.returncode == 0, stderr.decode(errors="replace")
                    await echo
                finally:
                    if process is not None and process.returncode is None:
                        process.kill()
                        await process.wait()
                    echo.cancel()
                    await asyncio.gather(echo, return_exceptions=True)

    asyncio.run(check())


def test_authored_config_and_protected_constructor(tmp_path):
    path = tmp_path / "local.toml"
    path.write_text(snippet("reference/config", "config_example"), encoding="utf-8")
    config = load_config(path)
    assert config.config_version == 2 and config.revision == 0
    assert set(config.networks) == {"default", "team"}
    assert config.networks["team"].join_verifier is None
    assert not config.permits("alice", "observer")
    assert config.permits("observer", "alice")
    assert config.allowed_names == ("alice", "bob", "observer")
    factory = python_example("reference/config", "protected_config")["protected_configuration"]
    assert factory(JOIN_TOKEN).networks["default"].join_verifier is not None


def test_authored_admin_create_revision_conflict_and_redaction(monkeypatch):
    create = python_example("reference/admin", "admin_example")["create_team"]

    async def check():
        async with running_example(monkeypatch) as relay:
            result = await create(relay.admin_endpoint, ADMIN_TOKEN)
            assert result.revision == 1
            async with await AdminClient.connect(
                relay.admin_endpoint, token=ADMIN_TOKEN,
            ) as admin:
                with pytest.raises(AdminError) as failure:
                    await admin.call("network.delete", {"network": "team"}, expected_revision=0)
                assert failure.value.code == "revision_conflict"
                assert failure.value.outcome == "no_effect"
                current = await admin.call("config.get")
                assert current.revision == 1
                assert current.result["networks"]["team"] == {"protected": False}
                assert "admin_verifier" not in current.result
                assert ADMIN_TOKEN not in str(current.result)
                async with (
                    await Node.connect("admin-alice", relay.endpoint) as alice,
                ):
                    await alice.join("team")
                    removed = await admin.call(
                        "member.remove", {"network": "team", "name": alice.name},
                        expected_revision=current.revision,
                    )
                    assert removed.revision == current.revision
                    assert removed.result["changed"] and removed.result["ephemeral"]

    asyncio.run(check())
