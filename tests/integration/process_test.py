import asyncio
import errno
import os
import signal
import socket
import sys
from contextlib import asynccontextmanager
from pathlib import Path

import pytest

from .helpers import TEST_ADMIN_VERIFIER


@asynccontextmanager
async def service(config: Path, *, env=None):
    environment = dict(os.environ)
    environment.pop("NODALWIRE_ADMIN_TOKEN", None)
    if env is not None:
        environment.update(env)
    process = await asyncio.create_subprocess_exec(
        sys.executable,
        "-m",
        "nodalwire",
        "serve",
        "--config",
        str(config),
        env=environment,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
    )
    try:
        endpoint = (await asyncio.wait_for(process.stdout.readline(), 5)).decode().strip()
        assert endpoint.startswith("tcp://127.0.0.1:"), (endpoint, await process.stderr.read())
        yield process, endpoint
    finally:
        if process.returncode is None:
            process.send_signal(signal.SIGTERM)
        try:
            await asyncio.wait_for(process.wait(), 3)
        except TimeoutError:
            process.kill()
            await process.wait()
            pytest.fail("relay did not shut down after SIGTERM")
        stderr = (await process.stderr.read()).decode()
        assert process.returncode == 0, stderr


def test_cli_service_and_two_application_processes_native_bytes(tmp_path: Path):
    async def check():
        config = tmp_path / "relay.toml"
        config.write_text(f'''config_version = 2
endpoint = "tcp://127.0.0.1:*"
admin_endpoint = "tcp://127.0.0.1:*"
admin_verifier = "{TEST_ADMIN_VERIFIER}"
''')
        children = []
        endpoint = ""
        try:
            async with service(config) as (_, endpoint):
                receiver = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-c",
                    """
import asyncio, sys
from nodalwire import Node
async def main():
    node = await Node.connect("receiver", sys.argv[1])
    try:
        print("READY", flush=True)
        message = await node.receive()
        print(message.sender, message.payload.hex(), flush=True)
    finally:
        await node.close()
asyncio.run(main())
""",
                    endpoint,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                children.append(receiver)
                # Actual receiver HELLO acknowledgement; no cross-peer admission sleep.
                assert await asyncio.wait_for(receiver.stdout.readline(), 5) == b"READY\n"
                sender = await asyncio.create_subprocess_exec(
                    sys.executable,
                    "-c",
                    """
import asyncio, sys
from nodalwire import Node
async def main():
    node = await Node.connect("sender", sys.argv[1])
    try:
        await node.send("receiver", bytes(range(256)) + b"\\x00process\\xff")
        print("QUEUED", flush=True)
    finally:
        await node.close()
asyncio.run(main())
""",
                    endpoint,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE,
                )
                children.append(sender)
                sender_out, sender_err = await asyncio.wait_for(sender.communicate(), 5)
                receiver_out, receiver_err = await asyncio.wait_for(receiver.communicate(), 5)
                assert sender.returncode == 0 and receiver.returncode == 0, (
                    sender_err + receiver_err
                )
                assert sender_out == b"QUEUED\n"
                source, hex_payload = receiver_out.decode().split()
                assert source == "sender"
                assert bytes.fromhex(hex_payload) == bytes(range(256)) + b"\x00process\xff"
        finally:
            for child in children:
                if child.returncode is None:
                    child.kill()
                    await child.wait()
        host, port = endpoint[6:].split(":")
        with socket.socket() as probe:
            probe.settimeout(1)
            assert probe.connect_ex((host, int(port))) == errno.ECONNREFUSED

    asyncio.run(check())
