"""Install actual local tarball; verify exports/types/native transport and real wire.

--skip-interop explicitly limits evidence to the installed Node artifact. Full
acceptance requires the default run against matching reviewed AR2 Python source.
NODALWIRE_PYTHON_SOURCE selects that tree's src/, NODALWIRE_ARTIFACT_DIR optionally
retains the checked tarball, NODALWIRE_EVIDENCE_DIR selects scratch placement.
"""

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

PACKAGE = Path(__file__).resolve().parents[1]
STORE = Path(os.environ.get(
    "NODALWIRE_PNPM_STORE", str(PACKAGE / "node_modules/.pnpm-store"),
)).resolve()


def run(args, cwd=PACKAGE, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=90)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-interop", action="store_true")
    args = parser.parse_args()
    scratch = os.environ.get("NODALWIRE_EVIDENCE_DIR")
    if scratch:
        Path(scratch).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="node-package-smoke-", dir=scratch) as temporary:
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
             'import { Node, RelayError, ReceiptTimeout, encodeEnvelope, decodeEnvelope } '
             'from "@devcapsule/nodalwire-client"; '
             'if (!Node || !RelayError || !ReceiptTimeout || !encodeEnvelope || !decodeEnvelope) '
             'throw Error("exports"); console.log("PASS installed ESM exports/native import");'],
            cwd=consumer)
        (consumer / "consumer.ts").write_text('''import {
  Node, encodeEnvelope, decodeEnvelope, type Envelope,
  type Message, type MembershipReceipt, type SendOptions,
} from "@devcapsule/nodalwire-client";
async function application() {
  const node = await Node.connect("typed", undefined, { inboxSize: 2 });
  const receipt: MembershipReceipt = await node.join("team", "fixture-token");
  const options: SendOptions = { network: receipt.network, timeout: 1 };
  await node.send("peer", Uint8Array.of(0, 255), options);
  const message: Message = await node.receive({ signal: AbortSignal.timeout(100) });
  const bytes: Uint8Array = message.payload;
  const queued: Message | undefined = node.receiveNowait();
  const response: Message = await node.request("peer", bytes, options);
  await node.reply(message, response.payload, { timeout: 1 });
  const envelope: Envelope = { kind: "request", id: "a".repeat(32), payload: bytes };
  const decoded: Envelope | undefined = decodeEnvelope(encodeEnvelope(envelope));
  console.log(message.sender, message.network, queued, decoded);
  // @ts-expect-error string is not a byte payload
  await node.send("peer", "not bytes");
  // @ts-expect-error callers cannot bypass admission
  new Node();
  // @ts-expect-error membership receipt is readonly
  receipt.changed = true;
  // @ts-expect-error reply cannot override the incoming network
  await node.reply(message, bytes, { network: "other" });
  await node.leave("team");
  await node.close();
}
void application;
''')
        run(["node", str(PACKAGE / "node_modules/typescript/bin/tsc"),
             "--noEmit", "--strict", "--module", "NodeNext", "--target", "ES2022",
             "consumer.ts"], cwd=consumer)
        print("PASS installed declarations: bytes/network/membership/request/codec contracts", flush=True)
        installed_root = consumer / "node_modules/@devcapsule/nodalwire-client"
        installed = installed_root / "dist/index.js"
        # Run real native fake-router/lifecycle tests through the installed artifact,
        # not just source dist. Consumer owns all copied test fixtures; no secrets
        # or dependency tree is copied.
        tests = installed_root / "tests"
        tests.mkdir()
        for source in (PACKAGE / "tests").glob("*.mjs"):
            shutil.copyfile(source, tests / source.name)
        run(["node", "--test", *map(str, sorted(tests.glob("*.test.mjs")))], cwd=consumer)
        if args.skip_interop:
            print("SKIP real Python wire: artifact-only run, NOT full interop acceptance", flush=True)
        else:
            run(["python", "tests/interop.py"], env={
                **os.environ, "NODALWIRE_CLIENT_MODULE": installed.as_uri(),
            })
        artifact_dir = os.environ.get("NODALWIRE_ARTIFACT_DIR")
        if artifact_dir:
            artifacts = Path(artifact_dir)
            artifacts.mkdir(parents=True, exist_ok=True)
            target = artifacts / tarball.name
            shutil.copyfile(tarball, target)
            print(f"PASS checked tarball retained: {target}", flush=True)


if __name__ == "__main__":
    main()
