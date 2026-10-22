"""Actual one-shot processes against owned relay; no coordination endpoint."""

import asyncio
import base64
import json
import os
import signal
import sys

import pytest

from nodalwire import AdminClient, Node
from nodalwire.config import load_config
from nodalwire.credentials import make_verifier

from .helpers import TEST_ADMIN_TOKEN, TEST_ADMIN_VERIFIER
from .process_test import service

JOIN = "cli-fixture-join"


def config_file(tmp_path):
    path = tmp_path / "relay.toml"
    path.write_text(f'''config_version=2
endpoint="tcp://127.0.0.1:*"
admin_endpoint="tcp://127.0.0.1:*"
admin_verifier="{TEST_ADMIN_VERIFIER}"
[networks.red]
join_verifier="{make_verifier(JOIN)}"
[networks.other]
''')
    return path


async def spawn(*args, env=None):
    environment = {**os.environ, "CLI_ADMIN": TEST_ADMIN_TOKEN, "CLI_JOIN": JOIN, **(env or {})}
    return await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "nodalwire",
        *map(str, args),
        env=environment,
        stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )


async def invoke(*args, input=b"", env=None):
    process = await spawn(*args, env=env)
    try:
        out, err = await asyncio.wait_for(process.communicate(input), 5)
        return process.returncode, [json.loads(line) for line in out.splitlines()], err
    finally:
        if process.returncode is None:
            process.kill()
            await process.wait()


async def status(process):
    return json.loads(await asyncio.wait_for(process.stdout.readline(), 5))


async def close_child(process):
    if process.returncode is None:
        process.kill()
        await process.wait()


def test_send_and_finite_receive_are_new_connections_with_explicit_joins(tmp_path):
    async def run():
        async with service(config_file(tmp_path)) as (server, endpoint):
            assert (await status(server))["event"] == "serving"
            receiver = await Node.connect("python-receiver", endpoint)
            await receiver.join("red", JOIN)
            try:
                code, events, err = await invoke(
                    "send",
                    "python-receiver",
                    "--name",
                    "once",
                    "--endpoint",
                    endpoint,
                    "--network",
                    "red",
                    "--join-token-env",
                    "CLI_JOIN",
                    input=bytes(range(256)),
                )
                assert code == 0 and err == b""
                assert events[0]["meaning"] == "native_queue_acceptance_only"
                message = await asyncio.wait_for(receiver.receive(), 1)
                assert message.network == "red" and message.payload == bytes(range(256))
                # Same name is released, but no membership survives its invocation.
                code, _, err = await invoke(
                    "send",
                    "python-receiver",
                    "--name",
                    "once",
                    "--endpoint",
                    endpoint,
                    "--network",
                    "red",
                    input=b"no-shared-membership",
                )
                assert code != 0 and json.loads(err)["error"] == "join_denied"
                child = await spawn(
                    "receive",
                    "--name",
                    "once",
                    "--endpoint",
                    endpoint,
                    "--network",
                    "red",
                    "--join-token-env",
                    "CLI_JOIN",
                    "--count",
                    "1",
                )
                try:
                    assert (await status(child))["event"] == "ready"
                    await receiver.send("once", b"\x00\xff", network="red")
                    out, err = await asyncio.wait_for(child.communicate(), 3)
                    assert child.returncode == 0 and err == b""
                    events = list(map(json.loads, out.splitlines()))
                    assert events[0]["event"] == "message" and events[0]["network"] == "red"
                    assert base64.b64decode(events[0]["payload"]) == b"\x00\xff"
                    assert events[1] == {"event": "complete", "received": 1}
                finally:
                    await close_child(child)
            finally:
                await receiver.close()

    asyncio.run(run())


def test_cli_request_retains_connection_and_emits_unrelated_and_reply(tmp_path):
    async def run():
        async with service(config_file(tmp_path)) as (server, endpoint):
            admin_endpoint = (await status(server))["admin_endpoint"]
            responder = await Node.connect("responder", endpoint)
            await responder.join("red", JOIN)
            child = await spawn(
                "request",
                "responder",
                "--name",
                "cli-requester",
                "--endpoint",
                endpoint,
                "--network",
                "red",
                "--join-token-env",
                "CLI_JOIN",
            )
            communication = asyncio.create_task(child.communicate(b"request\x00\xff"))
            try:
                incoming = await asyncio.wait_for(responder.receive(), 2)
                assert incoming.network == "red" and incoming.sender == "cli-requester"
                await responder.send(incoming.sender, b"unrelated", network="red")
                await responder.reply(incoming, b"reply\x00\xff")
                out, err = await asyncio.wait_for(communication, 3)
                assert child.returncode == 0 and err == b""
                events = list(map(json.loads, out.splitlines()))
                assert [item["event"] for item in events] == ["message", "reply"]
                assert base64.b64decode(events[0]["payload"]) == b"unrelated"
                assert base64.b64decode(events[1]["payload"]) == b"reply\x00\xff"
                async with await AdminClient.connect(
                    admin_endpoint, token=TEST_ADMIN_TOKEN
                ) as admin:
                    members = await admin.call("member.list", {"network": "red"})
                    assert members.result["members"] == ["responder"]
            finally:
                await close_child(child)
                await asyncio.gather(communication, return_exceptions=True)
                await responder.close()

    asyncio.run(run())


def test_reply_uses_explicit_received_metadata_new_invocation_and_incoming_network(tmp_path):
    async def run():
        async with service(config_file(tmp_path)) as (server, endpoint):
            await status(server)
            requester = await Node.connect("requester", endpoint)
            await requester.join("red", JOIN)
            child = await spawn(
                "receive",
                "--name",
                "answerer",
                "--endpoint",
                endpoint,
                "--network",
                "red",
                "--join-token-env",
                "CLI_JOIN",
            )
            waiting = None
            try:
                assert (await status(child))["event"] == "ready"
                waiting = asyncio.create_task(
                    requester.request("answerer", b"question", network="red", timeout=3)
                )
                out, err = await asyncio.wait_for(child.communicate(), 2)
                assert child.returncode == 0 and err == b""
                incoming, complete = map(json.loads, out.splitlines())
                assert complete["event"] == "complete"
                request_path = tmp_path / "incoming.json"
                request_path.write_text(json.dumps(incoming))
                code, events, err = await invoke(
                    "reply",
                    "--name",
                    "answerer",
                    "--endpoint",
                    endpoint,
                    "--join-token-env",
                    "CLI_JOIN",
                    "--request-file",
                    request_path,
                    input=b"answer",
                )
                assert code == 0 and err == b"" and events[0]["network"] == "red"
                assert (await waiting).payload == b"answer"
            finally:
                await close_child(child)
                if waiting is not None:
                    waiting.cancel()
                    await asyncio.gather(waiting, return_exceptions=True)
                await requester.close()

    asyncio.run(run())


def test_admin_same_file_rotation_revision_and_restart(tmp_path):
    async def run():
        config = config_file(tmp_path)
        async with service(config) as (server, endpoint):
            admin_endpoint = (await status(server))["admin_endpoint"]
            common = ("--endpoint", admin_endpoint, "--token-env", "CLI_ADMIN")
            code, events, err = await invoke("admin", "config.get", *common)
            assert code == 0 and err == b"" and events[0]["revision"] == 0
            text = json.dumps(events)
            assert "scrypt-v1" not in text and TEST_ADMIN_TOKEN not in text
            code, events, err = await invoke(
                "admin",
                "network.create",
                *common,
                "--network",
                "new",
                "--credential-env",
                "CLI_JOIN",
                "--expected-revision",
                "0",
            )
            assert code == 0 and err == b"" and events[0]["revision"] == 1
            assert load_config(config).networks["new"].join_verifier is not None
            code, _, err = await invoke(
                "admin", "network.delete", *common, "--network", "new", "--expected-revision", "0"
            )
            assert code == 1 and json.loads(err)["error"] == "revision_conflict"
            code, events, err = await invoke(
                "admin",
                "network.update",
                *common,
                "--network",
                "default",
                "--protected",
                "--credential-env",
                "CLI_JOIN",
                "--expected-revision",
                "1",
            )
            assert code == 0 and err == b"" and events[0]["result"]["protected"]
            code, events, err = await invoke(
                "admin",
                "network.update",
                *common,
                "--network",
                "default",
                "--no-protected",
                "--expected-revision",
                "2",
            )
            assert code == 0 and err == b"" and not events[0]["result"]["protected"]
            code, events, err = await invoke(
                "admin",
                "admin.rotate",
                *common,
                "--credential-env",
                "NEW_ADMIN",
                "--expected-revision",
                "3",
                env={"NEW_ADMIN": "new-cli-admin"},
            )
            assert code == 0 and err == b"" and events[0]["revision"] == 4
            code, _, err = await invoke("admin", "config.get", *common)
            assert code == 1 and json.loads(err)["error"] == "unauthorized"
        assert "new-cli-admin" not in config.read_text() and JOIN not in config.read_text()
        async with service(config) as (server, _):
            admin_endpoint = (await status(server))["admin_endpoint"]
            code, events, err = await invoke(
                "admin",
                "config.get",
                "--endpoint",
                admin_endpoint,
                "--token-env",
                "NEW_ADMIN",
                env={"NEW_ADMIN": "new-cli-admin"},
            )
            assert code == 0 and err == b"" and events[0]["revision"] == 4
        assert sorted(path.name for path in tmp_path.iterdir()) == ["relay.toml"]

    asyncio.run(run())


def test_env_managed_rotation_cli_is_rejected_without_persisting_environment(tmp_path):
    async def run():
        path = config_file(tmp_path)
        before = path.read_bytes()
        async with service(path, env={"NODALWIRE_ADMIN_TOKEN": "server-env-fixture"}) as (
            server,
            _,
        ):
            admin_endpoint = (await status(server))["admin_endpoint"]
            code, _, err = await invoke(
                "admin",
                "admin.rotate",
                "--endpoint",
                admin_endpoint,
                "--token-env",
                "SERVER_ENV",
                "--credential-env",
                "CLI_JOIN",
                "--expected-revision",
                "0",
                env={"SERVER_ENV": "server-env-fixture"},
            )
            assert code == 1
            assert json.loads(err)["error"] == "environment_managed"
            assert b"server-env-fixture" not in err
        assert path.read_bytes() == before

    asyncio.run(run())


@pytest.mark.parametrize("mode", ["unrelated-cap", "sigint", "timeout"])
def test_request_output_cutoff_and_sigint_are_uncertain_and_cleanup(tmp_path, mode):
    async def run():
        async with service(config_file(tmp_path)) as (server, endpoint):
            await status(server)
            responder = await Node.connect("responder", endpoint)
            child = await spawn(
                "request",
                "responder",
                "--name",
                "cancelled-cli",
                "--endpoint",
                endpoint,
                "--max-unrelated",
                "1",
                "--timeout",
                "0.15" if mode == "timeout" else "5",
            )
            communication = asyncio.create_task(child.communicate(b"request"))
            try:
                incoming = await asyncio.wait_for(responder.receive(), 2)
                if mode == "unrelated-cap":
                    await responder.send(incoming.sender, b"noise-1")
                    await responder.send(incoming.sender, b"noise-2")
                elif mode == "sigint":
                    child.send_signal(signal.SIGINT)
                out, err = await asyncio.wait_for(communication, 3)
                error = json.loads(err)
                assert error["outcome"] == "indeterminate"
                assert child.returncode == (130 if mode == "sigint" else 1)
                assert (
                    error["error"]
                    == {
                        "unrelated-cap": "output_limit",
                        "sigint": "cancelled",
                        "timeout": "deadline_exceeded",
                    }[mode]
                )
                if mode == "unrelated-cap":
                    assert len(out.splitlines()) == 1
                code, _, err = await invoke(
                    "send",
                    "responder",
                    "--name",
                    "cancelled-cli",
                    "--endpoint",
                    endpoint,
                    input=b"name-released",
                )
                assert code == 0 and err == b""
                assert (await responder.receive()).payload == b"name-released"
            finally:
                await close_child(child)
                await asyncio.gather(communication, return_exceptions=True)
                await responder.close()

    asyncio.run(run())


def test_help_and_startup_errors_are_secret_safe_and_on_correct_streams(tmp_path, monkeypatch):
    monkeypatch.delenv("NODALWIRE_ADMIN_TOKEN", raising=False)

    async def run():
        help_process = await spawn("request", "--help")
        try:
            out, err = await asyncio.wait_for(help_process.communicate(), 2)
            assert help_process.returncode == 0 and err == b""
            assert b"uncertain" in out and b"--join-token-env" in out
        finally:
            await close_child(help_process)
        missing = tmp_path / "missing-admin.toml"
        missing.write_text(
            'config_version=2\nendpoint="tcp://127.0.0.1:*"\nadmin_endpoint="tcp://127.0.0.1:*"\n'
        )
        code, events, err = await invoke("--config", missing)
        assert code == 2 and events == []
        assert json.loads(err)["error"] == "invalid_configuration_or_input"
        valid = config_file(tmp_path)
        for token in ("", "malformed fixture secret"):
            code, events, err = await invoke(
                "serve", "--config", valid, env={"NODALWIRE_ADMIN_TOKEN": token}
            )
            assert code == 2 and events == []
            assert b"Traceback" not in err and b"malformed fixture secret" not in err
        code, events, err = await invoke(
            "send",
            "nobody",
            "--name",
            "bounded-input",
            "--max-bytes",
            "2",
            input=b"private-payload",
        )
        assert code == 2 and events == [] and json.loads(err)["error"] == "invalid_input"
        assert b"private-payload" not in err

    asyncio.run(run())


@pytest.mark.skipif(
    not os.environ.get("NODALWIRE_NODE_CLIENT_MODULE"),
    reason="explicit reviewed Node artifact module required",
)
def test_real_node_and_cli_request_reply_both_directions(tmp_path):
    async def node_process(mode, endpoint):
        return await asyncio.create_subprocess_exec(
            "node",
            "--input-type=module",
            "-e",
            """
const {Node,decodeEnvelope} = await import(process.env.NODALWIRE_NODE_CLIENT_MODULE);
const mode=process.argv[1], endpoint=process.argv[2];
const node=await Node.connect(mode==='responder'?'node-responder':'node-requester',endpoint);
try {
 await node.join('red',process.env.CLI_JOIN);
 console.log('READY');
 if(mode==='responder') {
  const incoming=await node.receive({signal:AbortSignal.timeout(3000)});
  const envelope=decodeEnvelope(incoming.payload);
  await node.send(incoming.sender,Buffer.from('node-unrelated'),{network:incoming.network});
  await node.reply(incoming,envelope.payload);
 } else {
  const reply=await node.request('cli-answerer',Uint8Array.from([0,255,42]),
    {network:'red',timeout:3});
  console.log(JSON.stringify({network:reply.network,sender:reply.sender,
    payload:Buffer.from(reply.payload).toString('base64')}));
 }
} finally { await node.close(); }
""",
            mode,
            endpoint,
            env={**os.environ, "CLI_JOIN": JOIN},
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )

    async def run():
        async with service(config_file(tmp_path)) as (server, endpoint):
            await status(server)
            responder = await node_process("responder", endpoint)
            try:
                assert await asyncio.wait_for(responder.stdout.readline(), 2) == b"READY\n"
                code, events, err = await invoke(
                    "request",
                    "node-responder",
                    "--name",
                    "cli-requester",
                    "--endpoint",
                    endpoint,
                    "--network",
                    "red",
                    "--join-token-env",
                    "CLI_JOIN",
                    input=b"\0\xffnode",
                )
                assert code == 0 and err == b""
                assert [event["event"] for event in events] == ["message", "reply"]
                assert base64.b64decode(events[0]["payload"]) == b"node-unrelated"
                assert base64.b64decode(events[1]["payload"]) == b"\0\xffnode"
                _, err = await asyncio.wait_for(responder.communicate(), 2)
                assert responder.returncode == 0 and err == b""
            finally:
                await close_child(responder)
            receiver = await spawn(
                "receive",
                "--name",
                "cli-answerer",
                "--endpoint",
                endpoint,
                "--network",
                "red",
                "--join-token-env",
                "CLI_JOIN",
            )
            requester = None
            try:
                assert (await status(receiver))["event"] == "ready"
                requester = await node_process("requester", endpoint)
                assert await asyncio.wait_for(requester.stdout.readline(), 2) == b"READY\n"
                out, err = await asyncio.wait_for(receiver.communicate(), 2)
                assert receiver.returncode == 0 and err == b""
                incoming = json.loads(out.splitlines()[0])
                request_path = tmp_path / "node-incoming.json"
                request_path.write_text(json.dumps(incoming))
                code, _, err = await invoke(
                    "reply",
                    "--name",
                    "cli-answerer",
                    "--endpoint",
                    endpoint,
                    "--join-token-env",
                    "CLI_JOIN",
                    "--request-file",
                    request_path,
                    input=b"from-cli",
                )
                assert code == 0 and err == b""
                out, err = await asyncio.wait_for(requester.communicate(), 2)
                assert requester.returncode == 0 and err == b""
                reply = json.loads(out)
                assert reply["network"] == "red" and reply["sender"] == "cli-answerer"
                assert base64.b64decode(reply["payload"]) == b"from-cli"
            finally:
                await close_child(receiver)
                if requester is not None:
                    await close_child(requester)

    asyncio.run(run())


def test_blocked_stdin_and_stdout_obey_deadline_without_hanging(tmp_path):
    async def run():
        child = await spawn("send", "nobody", "--name", "stdin-deadline", "--timeout", "0.05")
        try:
            # Keep stdin open with no EOF; input must time out before any connect.
            await asyncio.wait_for(child.wait(), 2)
            assert child.returncode == 1
            assert json.loads(await child.stderr.read())["error"] == "deadline_exceeded"
        finally:
            await close_child(child)
        async with service(config_file(tmp_path)) as (server, endpoint):
            await status(server)
            sender = await Node.connect("sender", endpoint)
            child = await spawn(
                "receive", "--name", "stdout-deadline", "--endpoint", endpoint, "--timeout", "0.2"
            )
            try:
                assert (await status(child))["event"] == "ready"
                await sender.send("stdout-deadline", b"x" * 500000)
                # Stop consuming stdout; JSON pipe fills, write deadline still wins.
                await asyncio.wait_for(child.wait(), 2)
                assert child.returncode == 1
                assert json.loads(await child.stderr.read())["error"] == "deadline_exceeded"
                await child.stdout.read()
            finally:
                await close_child(child)
                await sender.close()

    asyncio.run(run())
