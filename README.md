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
