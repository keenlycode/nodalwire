# NodalWire

A loopback-only byte relay with explicit network membership and separate local
administration, designed for AI agents to use and maintain.

- Usage: [tests/usage/](tests/usage/)
- Python: [src/nodalwire/](src/nodalwire/)
- Node.js: [src/nodalwire/client/node/](src/nodalwire/client/node/)
- Membership/request examples: [tests/integration/membership_test.py](tests/integration/membership_test.py)
- Configuration/persistence: [src/nodalwire/config_store.py](src/nodalwire/config_store.py)
- Administrative API: [src/nodalwire/admin.py](src/nodalwire/admin.py)

All declared networks are open unless protected; a protected default requires an
explicit join. Credentials grant join/admin permission, not peer identity. Local
bearer authentication is not encryption. Startup requires an explicitly supplied
admin token (`NODALWIRE_ADMIN_TOKEN`) or configuration verifier; none is generated.
Transport/config version upgrades reject legacy wire/config rather than downgrade.

## Consumers: install into your own application

Version **0.2.0** requires matching Python and Node packages. Do not mix legacy
0.1 packages with this AR2 relay. Building or checking a source checkout does not
publish a release or establish registry availability.

For prepublication, offline or local-artifact use, obtain the matching wheel and
built Node tarball from your maintainer. In a new
application directory, with Python 3.12+, Node.js 24, uv and pnpm 12.5.1:

```sh
mkdir my-nodalwire-app
cd my-nodalwire-app
uv venv .venv
uv pip install --python .venv/bin/python /absolute/path/nodalwire-0.2.0-py3-none-any.whl
printf 'allowBuilds:\n  zeromq: true\n' > pnpm-workspace.yaml
pnpm add /absolute/path/devcapsule-nodalwire-client-0.2.0.tgz
```

Use `from nodalwire import Node` in Python and
`import { Node } from "@devcapsule/nodalwire-client"` in an `.mjs` application.
Run Python with `.venv/bin/python`; the installed relay is
`.venv/bin/nodalwire`. No checkout, Deno or TypeScript compiler is required by
these consumers. The Node dependency `zeromq` still requires its native binding
and lifecycle script; pnpm's explicit `allowBuilds` entry permits only that
package. Other package managers have their own script policies; platform/prebuilt
availability and fallback native-build prerequisites remain zeromq's concern.
These commands use a new directory; do not overwrite an existing app's policy.

Follow the [Getting Started walkthrough](src/docs-src/getting-started/index.html)
for the relay and two clients. Supply an administrator token before starting the
relay. Never start over an existing listener or connect 0.2 clients to a 0.1
relay; use a private v2 configuration with unused loopback ports when necessary.
Only after matching 0.2.0 artifacts are actually published would
`uv pip install --python .venv/bin/python nodalwire==0.2.0` and
`pnpm add @devcapsule/nodalwire-client@0.2.0` replace local artifact paths.

## Contributors: build from a checkout

Consumers do not perform these steps. From this repository, prepare locked
Python and Node development dependencies and build distributable artifacts:

```sh
uv sync --locked
pnpm -C src/nodalwire/client/node install --frozen-lockfile
pnpm -C src/nodalwire/client/node exec tsc -p tsconfig.json
uv build --out-dir /tmp/nodalwire-artifacts
pnpm -C src/nodalwire/client/node pack --pack-destination /tmp/nodalwire-artifacts
```

Install those artifacts into a separate application as above. Do not commit SDK
`dist/` by default. Deno orchestrates the existing SDK development/test tasks;
it is not an application runtime requirement.

## Maintainers: readiness is not publication

Inspect wheel/sdist/tarball contents, record versions and SHA256 hashes, and check
both installed packages outside the checkout. After building the wheel above:

```sh
NODALWIRE_EVIDENCE_DIR=/tmp python tests/integration/nodalwire/client/node/package_smoke.py \
  --python-artifact /tmp/nodalwire-artifacts/nodalwire-0.2.0-py3-none-any.whl
```

This builds/packs the SDK, installs a fresh external consumer, checks ESM/types
and native cases, then runs copied interoperability fixtures against an isolated
installed Python package. Python uses `-I`; package/metadata origins, versions
and source-path exclusion are checked. A task-managed interpreter's own standard
library may live in ignored task storage; package and consumer paths must remain
external, and repository source/direct-root import paths are rejected.
The default smoke run instead uses Python source;
`--skip-interop` establishes Node-artifact evidence only. Native dependency stores
must be prepared for its offline pnpm installation. Local passes do not certify
pristine machines, all supported Python versions/platforms or security. Rebuild
artifacts after README changes; package content and recorded hashes must match
the final reviewed diff. Publishing, tags and Git operations are separate approvals.

## Documentation and development checks

Maintained site inputs live in [src/docs-src/](src/docs-src/); isolated build
scripts and locked dependencies live in [src/tools/docs/](src/tools/docs/).
Root `docs/` is ignored local preview output, not tracked source-branch content.
Validated public output is prepared separately for the dedicated `docs` branch
root; generated site assets do not belong in `main`. The normal stable release
goal is matching 0.2.0 PyPI/npm packages, followed by approved documentation
publication. Package uploads, source/tag/docs pushes and Pages deployment require
separate final approval; local preparation does none of them.
See the [documentation tooling guide](src/tools/docs/README.md) for setup,
preview, component ownership, and optional owned-browser verification.

All maintained tests live under root `tests/`. Unit paths mirror source paths
relative to `src/`; whole-site, transport, and interoperability flows are
integration tests. After installing each project's locked development dependencies,
run these from the repository root:

```sh
# Core Python environment (pytest + NodalWire's runtime dependencies).
uv run --locked pytest

# Isolated docs environment: strict TypeScript, build, Node and Python docs tests.
pnpm --dir src/tools/docs verify

# Node SDK environment: build, native unit/integration, Python interoperability.
(cd src/nodalwire/client/node && deno task test)
# Additional packaged-consumer/types/interoperability check:
(cd src/nodalwire/client/node && deno task test:artifact)
```

These commands account for separate locked environments without adding docs
packages to NodalWire's runtime dependencies. Root pytest explicitly discovers
core module units, top-level core integration suites and usage tests (272 cases).
Docs renderer units and site navigation integration cases run via the docs
`verify` command in the Engrave/Jinja environment, alongside its Node suites.
Executable documentation examples run through the same command in the separate
locked core Python environment, where NodalWire and pytest are available.
Verification explicitly builds the development playground for existing design
checks, then finishes with a clean public build excluding `/design/`. This explicit collection boundary keeps default root pytest usable; it
does not skip docs tests within their configured runner. Run all environment
commands above rather than treating missing dependencies or browser skips as passes. Docs verification without
explicit owned-browser environment values reports browser suites as skipped;
it does not establish browser behavior proof.
