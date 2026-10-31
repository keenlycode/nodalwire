# NodalWire 0.3.0

Coordinated Python **0.3.0** and Node **0.3.0** release preparation. These notes
record the intended release contents; they are not evidence of registry
publication. Package upload, tags, canonical-branch integration and documentation
deployment require a separate release approval.

## What changes

- **Native message metadata:** NWM3 carries message `id` and optional `reply_to`
  separately from raw application payload bytes in both SDKs.
- **Native request correlation:** requests wait for a matching message ID, sender
  and network. Replies get a fresh ID and reference the incoming message ID.
  Unrelated and late messages remain available in the ordinary bounded inbox.
- **Accepted message IDs:** successful Python and Node `send`/`reply` operations
  return the generated message ID, after queue acceptance.
- **CLI messages:** receive/reply events include native message metadata. Help
  now includes a complete first-message walkthrough, command examples, parameter
  descriptions and administration/revision guidance. No startup or authentication
  requirement was relaxed.
- **Node development tooling:** Node.js, TypeScript and pnpm scripts replace the
  Deno task runner. The SDK ships compiled ESM and declarations; no SDK bundler
  or new dependency is needed. Browser documentation bundles continue using esbuild.
- **User documentation:** version-aware routing, task-oriented learning pages,
  API/admin/protocol references and accessible static messaging diagrams. Getting
  started follows install → relay → receive → send, without a source build.

## Breaking upgrade from Python 0.2.x / Node 0.2.0

1. Stop the old applications and relay, then upgrade the relay and **every**
   messaging client together to 0.3.0. NWM3 rejects AR2; mixed versions cannot
   communicate. There is no compatibility shim, automatic downgrade, translation,
   reconnect or replay. Keep the previous artifacts/configuration separately if
   you need a coordinated rollback; do not mix old clients with a new relay.
2. Remove NWR1 envelope imports, encoding and decoding. `Message.payload` is now
   raw application bytes, including bytes that happen to begin with `NWR1`.
   Use native `Message.id` and `Message.reply_to` for correlation. Python uses
   `None` and Node uses `undefined` when `reply_to` is absent.
3. Update consumers of `send` and `reply` return values to accept a message-ID
   string. Prefer SDK `request`/`reply` rather than reproducing correlation logic.
   A message ID is not authenticated identity or proof of remote work.
4. Regenerate saved CLI input files. A received message event has exactly
   `event`, `id`, `reply_to`, `network`, `sender`, and `payload`; payload remains
   base64 in CLI JSON. `reply --request-file` rejects old four-key events and
   malformed/duplicate fields before connecting.
5. Preserve configuration version **2** and NA1 administration: neither format
   changed. Continue supplying an admin credential explicitly, and join protected
   networks with their own credentials. A config file remains optional.

Queue acceptance is not delivery, processing or durability. Timeout/cancellation
can leave an uncertain outcome; do not automatically retry a possibly completed
operation. Bounded inboxes and pending-request limits still apply.

## Installation after publication

```sh
python -m pip install 'nodalwire==0.3.0'
npm install @devcapsule/nodalwire-client@0.3.0
```

Python requires **3.12+**; the Node ESM client supports **Node.js 24** and needs
its native `zeromq` dependency's install script. Consumers need no source checkout
or TypeScript compiler. For prepublication verification, install the built
wheel/tarball instead of assuming these versions are already in the registries.
The release-readiness report records actual artifact hashes and tested platforms;
source version strings alone establish neither publication nor certification.

---

## Released 0.2.1

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
