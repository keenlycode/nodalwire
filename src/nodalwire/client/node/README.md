# NodalWire Node client

ESM TypeScript byte client for the loopback-only NodalWire relay. Node.js 24;
Deno orchestrates development, not runtime execution. Package identity remains
`@devcapsule/nodalwire-client`; this worktree builds local version `0.3.0-dev.0`
for a matching NWM3 relay. NWM3 is a breaking protocol change; there is no fallback.

## Consumers: use the built artifact

This development worktree is not a released or publishable artifact. Any future
consumer instructions require a separate release decision and a matching NWM3
Python relay. Do not install a legacy client or relay with this breaking protocol.
For a separately approved local artifact, the consumer setup would use pnpm 12.5.1:

```sh
printf 'allowBuilds:\n  zeromq: true\n' > pnpm-workspace.yaml
pnpm add /absolute/path/to/approved-nwm3-client.tgz
```

Import the installed package by name, as below; applications do not need the
source checkout, Deno or a TypeScript compiler. The tarball ships compiled ESM
and declarations. Do not overwrite an existing application's script policy.

## Contributors: build the distribution

From a source checkout, not the consumer application:

```sh
cd src/nodalwire/client/node
pnpm install --frozen-lockfile --store-dir ./node_modules/.pnpm-store
deno task build
pnpm pack
```

Hand the resulting tarball to the consumer; do not commit generated `dist/` by
default. The root README describes matching Python artifact preparation and the
separate maintainer acceptance path. Building a tarball does not publish it.

The native `zeromq` install script is required. For pnpm versions requiring script
approval, allow only `zeromq` in the application's `pnpm-workspace.yaml`:
`allowBuilds: { zeromq: true }`. Platform/prebuilt availability belongs to zeromq;
other Node versions/platforms and Deno runtime execution are not supported here.

```ts
import { Node } from "@devcapsule/nodalwire-client";

const alice = await Node.connect("alice", "tcp://127.0.0.1:5555");
try {
  // Every nondefault network needs an explicit join, even when open.
  await alice.join("team");
  await alice.send("bob", Uint8Array.of(0, 255), { network: "team" });
  const incoming = await alice.receive({ signal: AbortSignal.timeout(5000) });
  await alice.send(incoming.sender, incoming.payload, { network: incoming.network });
} finally {
  await alice.close();
}
```

Start the Python relay separately with configured administration credentials.
An open default network is autojoined on connect. A protected default allows
registration with **zero memberships**; call `join("default", credential)` before
using it. A join credential grants membership permission, **not identity or name
ownership**. Names are globally unique only for the live registration. Network
credentials do not grant administration rights. This client exposes no admin API.
Bearer credentials do not encrypt traffic or protect against root/same-user memory
inspection; remote-host networking is deliberately unsupported.

## API

- `Node.connect(name, endpoint?, options?) -> Promise<Node>` waits for admission.
  Names/networks match ASCII `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}`. Only literal
  loopback TCP or `localhost` endpoints are accepted; no DNS resolution.
- `join(network, credential?, options?) -> Promise<MembershipReceipt>` adds one
  membership without removing others. Omit a credential for open networks;
  supplied credentials must contain 1–1024 printable ASCII bytes, without spaces
  or control characters. No credentials are sent on HELLO.
- `leave(network, options?) -> Promise<MembershipReceipt>` removes that membership,
  including default. Receipts have readonly `{ network, joined, changed }` fields.
  Repeated joins recheck current policy; already joined/absent returns
  `changed: false`. A receipt describes an instant, not future membership state.
- `send(destination, payload: Uint8Array, { network?, reply_to?, timeout?, signal? }?) ->
  Promise<string>` snapshots bytes synchronously and returns its generated message ID
  only after an empty SEND acceptance receipt.
  `Buffer` is supported. Omitted network selects **default only**, never another
  shared network. Both peers must belong to the selected network.
- `receive({ signal? }?) -> Promise<Message>` returns readonly metadata
  `{ id, sender, network, reply_to, payload }`; `reply_to` is `undefined` when absent.
  Payload is caller-owned mutable bytes.
- `receiveNowait() -> Message | undefined` removes one currently queued ordinary
  message. Empty returns `undefined`, even after close. It performs no native
  read and never takes a correlated reply from an active request.
- `close({ timeout?, signal? }?) -> Promise<void>` attempts release, then closes
  its socket and joins its native reader/writer even on timeout/cancellation.
  Repeated/concurrent close waits for shared cleanup without repeating release.
  Only the first close caller controls release cancellation/deadline. A failed
  release can leave the name registered until lease expiry.

Connect options use camelCase: `timeout=5` **seconds**, `sendHwm=64`,
`receiveHwm=64`, `inboxSize=64`, `maxPending=128`, optional `signal: AbortSignal`.
Per-operation timeout defaults to the connect timeout. Queue limits are positive
native integers; timeouts must be finite, positive and fit a native timer. Receive
uses cancellation rather than a separate timeout; use `AbortSignal.timeout(ms)`.
No authoritative memberships cache is exposed: administrators can remove members.

## Request/reply is client-layer correlation

```ts
// Requester: keep this connection alive until the matching reply or deadline.
const response = await alice.request("bob", Uint8Array.of(1, 2), {
  network: "team",
  timeout: 5,
});
console.log(response.network, response.sender, response.payload);

// Service: ordinary receive gives a native Message; reply targets its sender/network.
const incoming = await bob.receive();
const replyId = await bob.reply(incoming, Uint8Array.of(3, 4));
```

`request(destination, payload, { network?, timeout?, signal? }?) -> Promise<Message>`
returns the whole native matching reply Message. `reply(incoming, payload,
{ timeout?, signal? }?) -> Promise<string>` may reply to any valid Message, creates
a fresh ID and references `incoming.id` in `reply_to`; it permits no network
override. Payload and metadata are captured before awaiting. All payload bytes,
including NWR1-looking data, are opaque; no envelope codec is exported.

Request matching is registered before SEND and checks ID, expected sender,
network and reply kind. It proves no peer identity. One overall deadline includes
SEND acceptance and reply wait. The first terminal event wins: a reader-accepted
matching reply can complete before/without a routing receipt; its owned receipt
wait is canceled and consumed without canceling shared socket operations. Earlier
rejection, timeout or cancellation removes matching, so later replies become
ordinary messages. SEND success alone continues waiting for the reply.

Unrelated, malformed, unsolicited and late replies stay in the ordinary bounded
inbox. Drain `receive()` concurrently with requests; no matching reply can be
stolen by an ordinary receive consumer. Reply waiters and control receipt entries
have independent caps, each `maxPending`; there is no unbounded deferred stash.
A full inbox pauses the sole reader, including desired replies/control receipts,
and may cause an uncertain timeout. Never infer that an operation had no effect.

## Backpressure, errors and lifecycle

SEND success means acceptance into the destination's native queue, **not remote
receipt, execution or durability**. `RelayError.code` includes membership/routing
rejections (`join_denied`, `not_member`, `destination_not_member`,
`network_not_found`, `destination_full`, `destination_unavailable`, `route_denied`),
protocol/admission errors, and local `pending_full`, `local_queue_full`, `closed`,
`connection_failed`, `invalid_receipt`. Errors expose only safe codes, never
credential values. `ReceiptTimeout` explicitly means **effect uncertain**;
AbortSignal uses its reason. Cancellation, timeout and lifecycle interruption can
occur after forwarding. There is no reconnect, transparent retry, replay or daemon.

There is one ordered bounded inbox/native reader. One extra DATA may wait while
full, pausing all reads. Control receipts—including join/leave/close—can therefore
time out unless callers drain messages. Canceling receive removes only its waiter.
Queued data survives close and remains readable; an empty closed receive rejects
`closed`. Already native-accepted DATA may arrive after leave/admin removal;
policy/token rotation changes future joins only. No recall is promised.

There is no JavaScript outbound backlog. A second in-flight native send rejects
`local_queue_full` even below HWM (different scheduling from Python). Receipt
concurrency is possible after each write settles. HWM counts messages, not total
bytes; kernel buffers also contribute. Payload caps are enforced, but no
post-admission native MAXMSGSIZE claim is made. Heartbeats run every lease/3 and
may be skipped under pressure. Cleanup owns sockets/operations, not a global
zeromq context. No security audit or production-hardening claim is made.

## Development checks

Requires local dependencies, Node 24, Deno, Python with PyZMQ and the matching NWM3
server/Python source. From this directory:

```sh
deno task fmt --check
deno task lint
deno task check
deno task test:unit     # build + NWM3 fake-relay/native-client checks
NODALWIRE_PYTHON_SOURCE=/reviewed/nwm3/src deno task test:interop
NODALWIRE_PYTHON_SOURCE=/reviewed/nwm3/src deno task test
NODALWIRE_PYTHON_SOURCE=/reviewed/nwm3/src deno task test:artifact
```

All maintained tests live under repository-root `tests/`, not this package.
Atomic module suites mirror `src/nodalwire/client/node/src/` under
`tests/unit/nodalwire/client/node/src/`. Transport/relay and interoperability
suites live in `tests/integration/nodalwire/client/node/`; the fake relay helper
lives in `tests/helpers/nodalwire/client/node/`. Tasks resolve these locations
relative to this package and use its pinned dependencies.

Tests bind owned ephemeral endpoints, never the coordination relay. Native tests
run with Node, not Deno. TypeScript emits ESM/declarations into `dist/`.
Source interop requires `NODALWIRE_PYTHON_SOURCE` to name the exact reviewed NWM3
tree; the repository baseline may be incompatible. Focused fake-router tests alone
are not cross-language acceptance evidence.
`NODALWIRE_PYTHON_SOURCE=/reviewed/tree/src` selects the exact matching reviewed
Python source for source-mode interoperability without copying or editing it. `NODALWIRE_EVIDENCE_DIR` selects artifact
scratch placement, `NODALWIRE_ARTIFACT_DIR` optionally retains the tarball and
`NODALWIRE_PNPM_STORE` overrides the package-local dependency store. For an
explicit artifact-only check while Python is unavailable, run
`deno task test:artifact --skip-interop`; its output labels real wire tests
as skipped, not passed. For both packages installed outside the checkout, run
`NODALWIRE_EVIDENCE_DIR=/tmp deno task test:artifact --python-artifact /absolute/path/approved-nwm3-python.whl`.
This creates a fresh Python environment, uses `-I`, copies only interoperability
fixtures outside the repository and asserts installed provenance/version. Default
source-mode interop alone does not establish installed-Python acceptance. The
smoke's pnpm installation uses a prepared offline store; no cold-cache or broad
platform certification is implied.
