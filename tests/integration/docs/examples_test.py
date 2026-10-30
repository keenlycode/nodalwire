"""Execute the maintained Getting Started Python and Node examples together."""

import asyncio
import os
import re
import sys
from pathlib import Path

from nodalwire import Relay, RelayConfig

ROOT = Path(__file__).resolve().parents[3]
PAGE = ROOT / "src/docs-src/getting-started/index.html"


def _examples() -> tuple[str, str]:
    source = PAGE.read_text(encoding="utf-8")
    pattern = re.compile(
        r"\{% set (python_example|javascript_example) %\}(.*?)\{% endset %\}"
        r"\s*\{\{\s*code_block\(\1,",
        re.DOTALL,
    )
    examples = {name: code for name, code in pattern.findall(source)}
    assert set(examples) == {"python_example", "javascript_example"}
    assert all(code.endswith("\n") for code in examples.values())
    return examples["python_example"], examples["javascript_example"]


def test_getting_started_python_and_node_examples_exchange_bytes(monkeypatch, node_application):
    python_example, node_example = _examples()
    admin_token = "getting-started-test-admin-token"
    monkeypatch.setenv("NODALWIRE_ADMIN_TOKEN", admin_token)

    async def exercise():
        relay = Relay(RelayConfig(
            endpoint="tcp://127.0.0.1:*",
            admin_endpoint="tcp://127.0.0.1:*",
        ))
        endpoint = await relay.start()
        service = asyncio.create_task(relay.run())
        child_env = {
            **os.environ,
            "NODALWIRE_ENDPOINT": endpoint,
            "PYTHONPATH": str(ROOT / "src"),
            "NODE_NO_WARNINGS": "1",
        }
        python = await asyncio.create_subprocess_exec(
            sys.executable,
            "-c",
            python_example,
            cwd=node_application,
            env=child_env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        try:
            assert python.stdout is not None
            ready = await asyncio.wait_for(python.stdout.readline(), timeout=5)
            assert ready == b"Python is ready\n"

            node = await asyncio.create_subprocess_exec(
                "node",
                "--input-type=module",
                "-e",
                node_example,
                cwd=node_application,
                env=child_env,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            try:
                node_stdout, node_stderr = await asyncio.wait_for(
                    node.communicate(), timeout=10,
                )
                assert node.returncode == 0, node_stderr.decode(errors="replace")
                assert node_stdout == b"hello from Python\n"
            finally:
                if node.returncode is None:
                    node.kill()
                    await node.wait()

            python_stdout, python_stderr = await asyncio.wait_for(
                python.communicate(), timeout=5,
            )
            assert python.returncode == 0, python_stderr.decode(errors="replace")
            assert python_stdout == b"hello from Node\n"
        finally:
            if python.returncode is None:
                python.kill()
                await python.wait()
            service.cancel()
            await asyncio.gather(service, return_exceptions=True)
            await relay.close()

    asyncio.run(exercise())
