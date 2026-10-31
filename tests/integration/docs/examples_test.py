"""Execute the authored Getting started CLI exchange on an owned relay.

The relay uses ephemeral ports, never the user's default relay. Installation is
not performed here; this checks the commands against the executing environment.
The same test can also run in an existing published-release environment.
"""

import asyncio
import base64
import json
import os
import re
import shlex
import subprocess
import sys
from pathlib import Path

from nodalwire import Relay, RelayConfig

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "src/docs-src/getting-started/index.html"


def _example(name):
    source = PAGE.read_text(encoding="utf-8")
    match = re.search(
        r"\{% set " + re.escape(name) + r" %\}(.*?)\{% endset %\}",
        source, re.DOTALL,
    )
    assert match is not None, f"missing executable snippet: {name}"
    return match.group(1)


def test_getting_started_cli_commands_exchange_bytes(monkeypatch):
    receiver_args = shlex.split(_example("receive_example"))
    sender_pipeline = shlex.split(_example("send_example"))
    pipe = sender_pipeline.index("|")
    # Execute the actual printf command; do not substitute a hard-coded payload.
    payload = subprocess.check_output(sender_pipeline[:pipe])
    sender_args = sender_pipeline[pipe + 1:]
    assert receiver_args[0] == sender_args[0] == "nodalwire"
    monkeypatch.setenv("NODALWIRE_ADMIN_TOKEN", "getting-started-test-admin-token")

    async def exercise():
        async with Relay(RelayConfig(
            endpoint="tcp://127.0.0.1:*", admin_endpoint="tcp://127.0.0.1:*",
        )) as relay:
            service = asyncio.create_task(relay.run())
            children = []
            try:
                environment = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}

                async def spawn(args):
                    child = await asyncio.create_subprocess_exec(
                        sys.executable, "-m", "nodalwire", *args[1:],
                        "--endpoint", relay.endpoint, env=environment,
                        stdin=asyncio.subprocess.PIPE,
                        stdout=asyncio.subprocess.PIPE,
                        stderr=asyncio.subprocess.PIPE,
                    )
                    children.append(child)
                    return child

                receiver = await spawn(receiver_args)
                ready = json.loads(await asyncio.wait_for(receiver.stdout.readline(), 5))
                assert ready == {"event": "ready", "name": "bob", "network": "default"}
                sender = await spawn(sender_args)
                out, err = await asyncio.wait_for(sender.communicate(payload), 5)
                assert sender.returncode == 0, err.decode(errors="replace")
                assert json.loads(out)["event"] == "accepted"
                out, err = await asyncio.wait_for(receiver.communicate(), 5)
                assert receiver.returncode == 0, err.decode(errors="replace")
                message, complete = [json.loads(line) for line in out.splitlines()]
                assert message["event"] == "message"
                assert message["sender"] == "alice" and message["network"] == "default"
                assert base64.b64decode(message["payload"], validate=True) == payload == b"hello"
                assert complete == {"event": "complete", "received": 1}
            finally:
                for child in children:
                    if child.returncode is None:
                        child.kill()
                        await child.wait()
                service.cancel()
                await asyncio.gather(service, return_exceptions=True)
        assert relay.socket.closed and relay.admin_socket.closed and relay.context.closed

    asyncio.run(exercise())
