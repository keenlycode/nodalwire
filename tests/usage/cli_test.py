"""Executable example: one-shot CLI bytes to a persistent Python library peer."""

import asyncio
import json
import sys

from nodalwire import Node, Relay, RelayConfig
from nodalwire.config import NetworkConfig
from nodalwire.config_store import ConfigStore
from nodalwire.credentials import make_verifier


def test_one_shot_send_to_library_peer_on_selected_open_network():
    async def example():
        config = RelayConfig(
            endpoint="tcp://127.0.0.1:*",
            admin_endpoint="tcp://127.0.0.1:*",
            admin_verifier=make_verifier("usage-only-admin-token"),
            networks={"work": NetworkConfig()},
        )
        async with Relay(store=ConfigStore(config, environ={})) as relay:
            service = asyncio.create_task(relay.run())
            receiver = await Node.connect("library-peer", relay.endpoint)
            process = None
            try:
                await receiver.join("work")  # Even open nondefault networks require JOIN.
                process = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-m",
                    "nodalwire",
                    "send",
                    "library-peer",
                    "--name",
                    "one-shot",
                    "--endpoint",
                    relay.endpoint,
                    "--network",
                    "work",
                    stdin=asyncio.subprocess.PIPE,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                stdout, stderr = await asyncio.wait_for(process.communicate(b"hello\0\xff"), 3)
                assert process.returncode == 0 and stderr == b""
                assert json.loads(stdout)["meaning"] == "native_queue_acceptance_only"
                message = await receiver.receive()
                assert (message.network, message.sender, message.payload) == (
                    "work",
                    "one-shot",
                    b"hello\0\xff",
                )
                # This invocation has already disconnected. Persistent use belongs
                # to the library peer; another CLI command gets a new connection.
            finally:
                if process is not None and process.returncode is None:
                    process.kill()
                    await process.wait()
                await receiver.close()
                service.cancel()
                await asyncio.gather(service, return_exceptions=True)

    asyncio.run(example())
