# NodalWire

A loopback-only byte relay for local applications, with Python and Node.js
clients, explicit network membership, and separate authenticated administration.

## Install and send your first message

This source prepares **NodalWire 0.3.0**: Python `nodalwire==0.3.0` and Node
`@devcapsule/nodalwire-client@0.3.0`. Building or testing this checkout does not
publish either package. The registry commands below apply after publication;
prepublication consumers can install the verified local artifacts instead.

Python requires **3.12+**. With [uv](https://docs.astral.sh/uv/):

```sh
uv tool install 'nodalwire==0.3.0'
```

In Terminal 1, generate a private admin credential and start the relay:

```sh
export NODALWIRE_ADMIN_TOKEN="$(python3 -c 'import secrets; print(secrets.token_hex(32))')"
nodalwire serve
```

No config file is required. Leave the relay running. In Terminal 2:

```sh
nodalwire receive --name bob --timeout 60
```

Wait for the `ready` event, then in Terminal 3:

```sh
printf 'hello' | nodalwire send bob --name alice
```

Bob receives a JSON message event with base64 payload `aGVsbG8=` (`hello`).
`accepted` means relay queue acceptance, not application processing or durable
storage. Both client commands exit after the exchange. Stop the relay with
Ctrl-C. Run `nodalwire --help` or `nodalwire COMMAND --help` for more examples.

For applications, install `nodalwire==0.3.0` into the application's Python
virtual environment and use `from nodalwire import Node`. For Node.js **24**:

```sh
npm install @devcapsule/nodalwire-client@0.3.0
```

Use `import { Node } from "@devcapsule/nodalwire-client"` from an ESM application.
No source checkout, Deno or TypeScript compiler is required by consumers. The
native `zeromq` dependency needs its installation script; with pnpm, explicitly
allow only `zeromq` in your application's script policy. Do not overwrite an
existing policy. Native prebuild/fallback availability is platform-dependent.

## Upgrading from 0.2.x

**Upgrade the relay and every messaging client together.** Version 0.3.0 uses
NWM3 and cannot communicate with the AR2 protocol in Python 0.2.x / Node 0.2.0.
There is no rolling mixed-version mode, downgrade, translation, reconnect or
replay. See [release and migration notes](RELEASE_NOTES.md) for the API changes.
NA1 administration and configuration version 2 remain unchanged.

The relay is loopback-only. Credentials grant join/admin permission, not peer-name
identity or encryption. Startup requires `NODALWIRE_ADMIN_TOKEN` or a configured
admin verifier; the server does not generate or reveal a secret. Every declared
network is open unless protected. A protected default requires an explicit join.

## Documentation

- [Getting started](src/docs-src/getting-started/index.html)
- [Messaging](src/docs-src/messaging/index.html)
- [Python and Node API](src/docs-src/reference/api/index.html)
- [Configuration](src/docs-src/reference/config/index.html)
- [Node package guide](src/nodalwire/client/node/README.md)
- [Executable usage examples](tests/usage/)

Maintained site inputs are in `src/docs-src/`. Root `docs/` is ignored generated
output, not source-branch content. The [docs tooling guide](src/tools/docs/README.md)
explains local builds, release previews and the separate publishing boundary.

## Contributors: build from a checkout

Consumers do not perform these steps. Prepare the locked environments first:

```sh
uv sync --locked
pnpm -C src/nodalwire/client/node install --frozen-lockfile
(cd src/nodalwire/client/node && deno task build)
uv build --out-dir /tmp/nodalwire-artifacts
pnpm -C src/nodalwire/client/node pack --pack-destination /tmp/nodalwire-artifacts
```

Install the wheel or tarball into a separate consumer environment for testing.
For example, `uv pip install --python /path/to/venv/bin/python
/tmp/nodalwire-artifacts/nodalwire-0.3.0-py3-none-any.whl` installs the local Python
artifact. Do not commit generated SDK `dist/` by default. Deno orchestrates SDK
development checks, not application execution.

```sh
uv run --locked --no-sync pytest
pnpm --dir src/tools/docs verify
(cd src/nodalwire/client/node && NODALWIRE_PYTHON_SOURCE="$PWD/../../.." deno task test)
NODALWIRE_EVIDENCE_DIR=/tmp uv run --locked --no-sync python \
  tests/integration/nodalwire/client/node/package_smoke.py \
  --python-artifact /tmp/nodalwire-artifacts/nodalwire-0.3.0-py3-none-any.whl \
  --python-version 0.3.0
```

The package smoke check installs both built packages outside the checkout,
checks their origins/versions, exercises declarations and native cases, and runs
cross-language fixtures with isolated Python imports. It requires a prepared
local pnpm dependency store; offline success is not a cold-cache/platform claim.
Source-mode interop alone is not installed-artifact verification.

All maintained tests live under `tests/`. Core pytest, isolated docs tooling, and
Node checks have separate collection/environment boundaries. Docs verification
builds the playground for its design tests, then restores product-only output.
Browser suites require an explicitly owned browser/CDP endpoint; a skipped suite
is not browser proof. No security-audit or exhaustive crash/power-loss claim is made.

## Maintainers: preparation is not publication

Record exact commits, artifact contents, versions, SHA256 hashes, installed-package
results and coverage limits before release approval. Then obtain separate approval
for package uploads, source/tag/docs pushes and deployment. Verify both registry
versions before presenting the matching documentation as a published release.
Keep the existing publishing-branch history; do not force-push or place generated
site assets in `main`.
