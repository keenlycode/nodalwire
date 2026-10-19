"""Pack/install the actual artifact locally; verify exports, types and Python wire."""

import json
import os
from pathlib import Path
import subprocess
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]
ROOT = PACKAGE.parents[3]
EVIDENCE = ROOT / ".agents/var/task-space/nodalwire-runtime-check/implementation"
STORE = Path(os.environ.get("NODALWIRE_PNPM_STORE", str(EVIDENCE / "pnpm-store")))


def run(args, cwd=PACKAGE, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=45)


EVIDENCE.mkdir(parents=True, exist_ok=True)
with tempfile.TemporaryDirectory(prefix="package-smoke-", dir=EVIDENCE) as temporary:
    work = Path(temporary)
    run(["deno", "task", "build"])
    run(["pnpm", "pack", "--pack-destination", str(work)])
    tarball, = work.glob("*.tgz")
    consumer = work / "consumer"
    consumer.mkdir()
    (consumer / "package.json").write_text(json.dumps({
        "private": True, "type": "module", "dependencies": {
            "@devcapsule/nodalwire-client": f"file:{tarball}",
        },
    }))
    (consumer / "pnpm-workspace.yaml").write_text("allowBuilds:\n  zeromq: true\n")
    run(["pnpm", "install", "--offline", "--store-dir", str(STORE)], cwd=consumer)
    run(["node", "--input-type=module", "-e",
         'import { Node, RelayError, ReceiptTimeout } from "@devcapsule/nodalwire-client"; '
         'if (!Node || !RelayError || !ReceiptTimeout) throw Error("exports"); '
         'console.log("PASS installed ESM exports/native import");'], cwd=consumer)
    (consumer / "consumer.ts").write_text('''import { Node, type Message } from "@devcapsule/nodalwire-client";
async function application() {
  const node = await Node.connect("typed", undefined, { inboxSize: 2 });
  await node.send("peer", Uint8Array.of(0, 255), { timeout: 1 });
  const message: Message = await node.receive({ signal: AbortSignal.timeout(100) });
  const bytes: Uint8Array = message.payload;
  console.log(message.sender, bytes);
  // @ts-expect-error string is not a byte payload
  await node.send("peer", "not bytes");
  // @ts-expect-error callers cannot bypass admission
  new Node();
  await node.close();
}
void application;
''')
    run(["node", str(PACKAGE / "node_modules/typescript/bin/tsc"),
         "--noEmit", "--strict", "--module", "NodeNext", "--target", "ES2022",
         "consumer.ts"], cwd=consumer)
    print("PASS installed declarations and byte-only type contract", flush=True)
    installed = consumer / "node_modules/@devcapsule/nodalwire-client/dist/index.js"
    run(["python", "tests/interop.py"], env={
        **os.environ, "NODALWIRE_CLIENT_MODULE": installed.as_uri(),
    })
    # Retain the exact verified artifact; TemporaryDirectory removes only our install.
    artifacts = EVIDENCE / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / tarball.name).write_bytes(tarball.read_bytes())
    print(f"PASS packed artifact retained: {artifacts / tarball.name}", flush=True)
