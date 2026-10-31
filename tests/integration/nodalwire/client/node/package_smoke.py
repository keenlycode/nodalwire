"""Install actual local tarball; verify exports/types/native transport and real wire.

--skip-interop explicitly limits evidence to the installed Node artifact.
Default interop uses the explicitly selected matching reviewed NWM3 Python source. --python-artifact installs
matching Python into a fresh external venv and runs copied interop fixtures there
with isolated imports, proving both installed packages instead of Python source.
NODALWIRE_PYTHON_SOURCE selects source-mode src/, NODALWIRE_ARTIFACT_DIR optionally
retains the checked tarball, NODALWIRE_EVIDENCE_DIR selects scratch placement.
"""

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from email.parser import BytesParser
from email.policy import default
from pathlib import Path
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[5]
PACKAGE = ROOT / "src" / "nodalwire" / "client" / "node"
STORE = Path(os.environ.get(
    "NODALWIRE_PNPM_STORE", str(PACKAGE / "node_modules/.pnpm-store"),
)).resolve()


def run(args, cwd=PACKAGE, env=None):
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=90)


def stage_native_fixtures(fixture_root, installed_root):
    """Mirror only public SDK test fixtures; every SDK import uses the artifact."""
    sdk = fixture_root / "src/nodalwire/client/node"
    sdk.parent.mkdir(parents=True)
    sdk.symlink_to(installed_root.resolve(), target_is_directory=True)
    fixture = fixture_root / "tests/fixtures/nwm3/wire.json"
    fixture.parent.mkdir(parents=True)
    shutil.copyfile(ROOT / "tests/fixtures/nwm3/wire.json", fixture)
    copied = []
    for relative, pattern in (
        ("tests/unit/nodalwire/client/node/src", "*.test.mjs"),
        ("tests/integration/nodalwire/client/node", "*.test.mjs"),
        ("tests/helpers/nodalwire/client/node", "*.mjs"),
    ):
        destination = fixture_root / relative
        destination.mkdir(parents=True)
        for source in sorted((ROOT / relative).glob(pattern)):
            target = destination / source.name
            shutil.copyfile(source, target)
            copied.append(target)
    native_tests = sorted(path for path in copied if path.name.endswith(".test.mjs"))
    assert len(native_tests) == 10, "Expected all ten split SDK native suite files"
    artifact = installed_root.resolve()
    assert artifact != PACKAGE.resolve(), "Fixtures must not target the source SDK"
    assert sdk.resolve() == artifact
    for module in copied:
        artifact_imports = 0
        for specifier in re.findall(r'from\s+["\']([^"\']+)["\']', module.read_text()):
            if "/src/nodalwire/client/node/dist/" in specifier:
                target = (module.parent / specifier).resolve(strict=True)
                assert target.is_relative_to(artifact), f"Non-artifact SDK import: {target}"
                artifact_imports += 1
        if module in native_tests:
            assert artifact_imports, f"Suite does not import the installed artifact: {module}"
    # deps.mjs anchors createRequire here, so native zeromq also uses the install.
    assert (sdk / "package.json").resolve(strict=True).is_relative_to(artifact)
    return native_tests


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-interop", action="store_true")
    parser.add_argument("--python-artifact", type=Path,
                        help="Install a matching Python wheel for isolated interop")
    parser.add_argument("--python-version",
                        help="Expected nodalwire Python distribution version for --python-artifact")
    args = parser.parse_args()
    if (
        not args.skip_interop and not args.python_artifact and
        not os.environ.get("NODALWIRE_PYTHON_SOURCE")
    ):
        parser.error("source interop requires NODALWIRE_PYTHON_SOURCE for the reviewed NWM3 tree")
    if args.python_version and not args.python_artifact:
        parser.error("--python-version is only valid with --python-artifact")
    if args.python_artifact:
        if args.skip_interop:
            parser.error("--python-artifact cannot be combined with --skip-interop")
        if not args.python_version:
            parser.error("--python-artifact requires its own explicit --python-version")
        args.python_artifact = args.python_artifact.resolve()
        if not args.python_artifact.is_file() or args.python_artifact.suffix != ".whl":
            parser.error("--python-artifact must name an existing wheel")
        try:
            with ZipFile(args.python_artifact) as archive:
                metadata_paths = [path for path in archive.namelist()
                                  if path.endswith(".dist-info/METADATA")]
                if len(metadata_paths) != 1:
                    raise ValueError("wheel must contain exactly one dist-info/METADATA")
                metadata = BytesParser(policy=default).parsebytes(
                    archive.read(metadata_paths[0])
                )
        except (OSError, ValueError) as error:
            parser.error(f"invalid Python wheel metadata: {error}")
        if metadata["Name"] != "nodalwire" or metadata["Version"] != args.python_version:
            parser.error(
                "Python wheel metadata does not match its independent expected name/version"
            )
    node_expected_version = json.loads((PACKAGE / "package.json").read_text())["version"]
    scratch = os.environ.get("NODALWIRE_EVIDENCE_DIR")
    if scratch:
        Path(scratch).mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="node-package-smoke-", dir=scratch) as temporary:
        work = Path(temporary)
        if args.python_artifact and work.resolve().is_relative_to(ROOT.resolve()):
            parser.error("Installed-package evidence directory must be outside checkout")
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
             'import { Node, RelayError, ReceiptTimeout } '
             'from "@devcapsule/nodalwire-client"; '
             'if (!Node || !RelayError || !ReceiptTimeout) '
             'throw Error("exports"); console.log("PASS installed ESM exports/native import");'],
            cwd=consumer)
        (consumer / "consumer.ts").write_text('''import {
  Node, type Message, type MembershipReceipt, type RequestOptions, type SendOptions,
} from "@devcapsule/nodalwire-client";
async function application() {
  const node = await Node.connect("typed", undefined, { inboxSize: 2 });
  const receipt: MembershipReceipt = await node.join("team", "fixture-token");
  const options: SendOptions = { network: receipt.network, timeout: 1 };
  const acceptedId: string = await node.send("peer", Uint8Array.of(0, 255), options);
  const requestOptions: RequestOptions = { network: receipt.network, timeout: 1 };
  const message: Message = await node.receive({ signal: AbortSignal.timeout(100) });
  const bytes: Uint8Array = message.payload;
  const queued: Message | undefined = node.receiveNowait();
  const response: Message = await node.request("peer", bytes, requestOptions);
  const replyId: string = await node.reply(message, response.payload, { timeout: 1 });
  console.log(message.id, message.reply_to, message.sender, message.network, queued, acceptedId, replyId);
  // @ts-expect-error string is not a byte payload
  await node.send("peer", "not bytes");
  // @ts-expect-error callers cannot bypass admission
  new Node();
  // @ts-expect-error membership receipt is readonly
  receipt.changed = true;
  // @ts-expect-error reply cannot override the incoming network
  await node.reply(message, bytes, { network: "other" });
  // @ts-expect-error request has no caller-supplied correlation ID
  await node.request("peer", bytes, { reply_to: "a".repeat(32) });
  // @ts-expect-error send has no caller-supplied message ID
  await node.send("peer", bytes, { id: "a".repeat(32) });
  await node.leave("team");
  await node.close();
}
void application;
''')
        run(["node", str(PACKAGE / "node_modules/typescript/bin/tsc"),
             "--noEmit", "--strict", "--module", "NodeNext", "--target", "ES2022",
             "consumer.ts"], cwd=consumer)
        print("PASS installed declarations: bytes/network/membership/request/reply metadata contracts",
              flush=True)
        installed_root = consumer / "node_modules/@devcapsule/nodalwire-client"
        installed_root_resolved = installed_root.resolve(strict=True)
        assert installed_root_resolved.is_relative_to(consumer.resolve())
        node_metadata = json.loads((installed_root_resolved / "package.json").read_text())
        assert node_metadata["name"] == "@devcapsule/nodalwire-client"
        assert node_metadata["version"] == node_expected_version
        print(f"PASS installed Node provenance: version={node_metadata['version']}; "
              f"package={installed_root_resolved}", flush=True)
        installed = installed_root / "dist/index.js"
        # Preserve root-relative fixture imports without changing any test body.
        # The scratch src SDK link targets the consumer install, never project dist.
        native_tests = stage_native_fixtures(work / "fixture-root", installed_root)
        native = subprocess.run(
            ["node", "--test", "--test-reporter=tap", *map(str, native_tests)],
            cwd=consumer, capture_output=True, text=True, timeout=90,
        )
        print(native.stdout, end="", flush=True)
        print(native.stderr, end="", file=sys.stderr, flush=True)
        native.check_returncode()
        assert re.search(r"^# tests 27$", native.stdout, re.MULTILINE), (
            "Expected all 27 native cases")
        assert re.search(r"^# pass 27$", native.stdout, re.MULTILINE), (
            "All 27 artifact cases must pass")
        assert re.search(r"^# skipped 0$", native.stdout, re.MULTILINE), (
            "Artifact cases must not skip")
        if args.skip_interop:
            print("SKIP real Python wire: artifact-only run, NOT full interop acceptance",
                  flush=True)
        elif args.python_artifact:
            venv = work / "python-consumer"
            run(["uv", "venv", "--python", sys.executable, str(venv)], cwd=consumer)
            python = venv / "bin/python"
            clean_env = {key: value for key, value in os.environ.items()
                         if key not in {"PYTHONPATH", "PYTHONHOME", "NODALWIRE_PYTHON_SOURCE"}}
            run(["uv", "pip", "install", "--python", str(python),
                 str(args.python_artifact)], cwd=consumer, env=clean_env)
            fixtures = work / "interop"
            fixtures.mkdir()
            for name in ("interop.py", "interop.mjs"):
                shutil.copyfile(Path(__file__).with_name(name), fixtures / name)
            run([str(python), "-I", str(fixtures / "interop.py")], cwd=consumer, env={
                **clean_env,
                "NODALWIRE_CLIENT_MODULE": installed.as_uri(),
                "NODALWIRE_PYTHON_INSTALLED": "1",
                "NODALWIRE_FORBIDDEN_SOURCE": str(ROOT),
                "NODALWIRE_EXPECTED_VERSION": args.python_version,
            })
        else:
            run([sys.executable, str(Path(__file__).with_name("interop.py"))], env={
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
