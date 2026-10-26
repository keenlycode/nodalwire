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

## Documentation and development checks

Maintained site inputs live in [src/docs-src/](src/docs-src/); isolated build
scripts and locked dependencies live in [src/tools/docs/](src/tools/docs/).
Root [docs/](docs/) is generated GitHub Pages output, not maintained source.
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
