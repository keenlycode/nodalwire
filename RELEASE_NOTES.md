# NodalWire 0.2.1

Python-only patch release. The Python relay version is 0.2.1; the Node package
remains 0.2.0. Source preparation does not establish registry availability;
publication and deployment are separate approved operations.

## Changes

- Bare `nodalwire` now displays help and exits instead of starting a relay.
  Explicitly start the relay with `nodalwire serve`; callers that previously
  passed root-level `--config` must use `nodalwire serve --config`.
- No wire protocol, Node package, or network behavior change.

## Python installation

After publication, install with `python -m pip install 'nodalwire==0.2.1'`.
Python requires 3.12 or newer.

## Previous 0.2.0 release

Stable 0.2.0 release notes follow; they describe the shared protocol and Node
package, which remain at 0.2.0.


## Changes

- Explicit additive network membership, with open networks by default and optional
  join credentials for any network, including `default`.
- Separate loopback-only administration: network policy and credential rotation,
  member inspection/removal, and revision-fenced, verifier-only persistence in the
  explicitly supplied configuration file.
- Matching Python and Node membership and bounded request/reply APIs.
- Bounded one-shot Python CLI operations for send, receive, request, reply and
  administration. No daemon, reconnect, automatic retry or replay.

## Migration from 0.1.0

1. Upgrade the Python relay and all Python/Node consumers together to `0.2.0`.
   AR2 transport and `config_version = 2` intentionally reject legacy wire/config
   formats; mixed `0.1.0`/`0.2.0` deployments are unsupported. Plan a coordinated
   restart rather than a rolling upgrade.
2. Recreate legacy configuration in the new format; there is no automatic
   conversion. Use `tests/usage/local.toml` and `tests/usage/config_test.py` as the
   configuration examples. Preserve the old file separately before migration.
3. Supply administration credentials explicitly through `NODALWIRE_ADMIN_TOKEN`
   or the configuration verifier. No secret is generated or revealed. An empty or
   malformed environment override fails instead of falling back to the file.
4. Join each nondefault network explicitly. An open default is autojoined;
   a protected default admits a client with zero memberships until it explicitly
   joins. Sending without a network selects literal `default`, not another shared
   network. Do not treat configuration as a static peer-membership list.
5. Drain ordinary messages while issuing requests. Replies use the incoming
   message's network; unrelated and late messages remain in the bounded inbox.
   A one-shot CLI requester must remain running until its response arrives.
6. Handle uncertain outcomes: native queue acceptance is not remote execution or
   durability. Cancellation, timeouts and crashes do not prove no effect. Rotation
   changes future joins, not existing memberships; removal cannot recall already
   accepted messages. Do not automatically replay uncertain operations.

After publication, the corresponding installation commands are:

```sh
python -m pip install 'nodalwire==0.2.1'
npm install @devcapsule/nodalwire-client@0.2.0
```

Python requires 3.12 or newer. The Node client supports Node.js 24 (ESM and
TypeScript declarations) and requires its native `zeromq` dependency. With pnpm,
allow the `zeromq` build script when script approval is required. The Node package
has no administration API; use the Python API or CLI for administration.

## Security and support boundary

The relay is loopback-only. Credentials grant join/admin permission, not peer-name
identity; bearer authentication is not encryption or protection from same-user/root
memory inspection. No security-audit or exhaustive crash/power-loss claim is made.

The preceding feature validation covered Linux x64, Python 3.12.13/3.14.8 and
producer 3.15.0, plus Node 24.22.1. Release-artifact preparation results and hashes
are recorded separately; repeated artifact/interpreter cases are not unique tests.
