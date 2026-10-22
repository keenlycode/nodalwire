# NodalWire Node client

ESM TypeScript byte client for the loopback-only NodalWire relay. Node.js 24;
Deno orchestrates development, not runtime execution. Package identity remains
`@devcapsule/nodalwire-client`; `0.2.0-dev.0` is an unpublished development version.
AR2 is intentionally incompatible with AR1: neither endpoint silently downgrades.

## Build and use

Install an explicitly built local artifact (no publication is required):

```sh
cd src/nodalwire/client/node
pnpm install --frozen-lockfile --store-dir ./node_modules/.pnpm-store
deno task build
pnpm pack
# From your application:
pnpm add /absolute/path/to/devcapsule-nodalwire-client-0.2.0-dev.0.tgz
```

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
- `send(destination, payload: Uint8Array, { network?, timeout?, signal? }?) ->
  Promise<void>` snapshots bytes synchronously, preserving subarray bounds.
  `Buffer` is supported. Omitted network selects **default only**, never another
  shared network. Both peers must belong to the selected network.
- `receive({ signal? }?) -> Promise<Message>` returns readonly metadata
  `{ network, sender, payload }`. Payload is caller-owned mutable bytes.
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

// Service: ordinary receive gives opaque bytes; reply validates a request envelope.
const incoming = await bob.receive();
await bob.reply(incoming, Uint8Array.of(3, 4)); // always incoming.network
```

`request(destination, payload, { network?, timeout?, signal? }?) -> Promise<Message>`
returns decoded reply payload with original sender/network. `reply(incoming,
payload, { timeout?, signal? }?) -> Promise<void>` requires a valid request
message and permits no network override. Incoming metadata/envelope ID and outgoing
bytes are captured before awaiting. Ordinary `receive` never decodes payloads.

Exported `encodeEnvelope(envelope, maxBytes=1048576) -> Uint8Array` and
`decodeEnvelope(bytes, maxBytes=1048576) -> Envelope | undefined` use readonly
`Envelope { kind: "request" | "reply", id: string, payload: Uint8Array }`. Wire
bytes are `NWR1\n` plus UTF-8 JSON with exactly `v:1`, `kind`, a 32-lowercase-hex
random ID and canonical padded base64 `payload`. Duplicate keys, invalid UTF-8,
extra fields and noncanonical base64 are not envelopes. Invalid encode input is
`TypeError`; encoded size above the cap is `RelayError("payload_too_large")`.
Decoding invalid/oversize data returns `undefined`; clients use negotiated limits.

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

Requires local dependencies, Node 24, Deno, Python with PyZMQ and the matching AR2
server/Python source. From this directory:

```sh
deno fmt --check src tests deno.json tsconfig.json package.json
deno task lint
deno task check
deno task build
node --test tests/*.test.mjs   # independent fake-router/lifecycle/codec checks
python tests/interop.py       # real Python relay/client interoperability
deno task test               # build + both check sets above
python tests/package_smoke.py # pack/install consumer, types + real interop
```

Tests bind owned ephemeral endpoints, never the coordination relay. Native tests
run with Node, not Deno. TypeScript emits ESM/declarations into `dist/`.
Interoperability/artifact checks depend on matching Python/server implementation;
focused fake-router tests alone are not cross-language acceptance evidence.
`NODALWIRE_PYTHON_SOURCE=/reviewed/tree/src` can select matching reviewed Python
source without copying or editing it. `NODALWIRE_EVIDENCE_DIR` selects artifact
scratch placement, `NODALWIRE_ARTIFACT_DIR` optionally retains the tarball and
`NODALWIRE_PNPM_STORE` overrides the package-local dependency store. For an
explicit artifact-only check while Python is unavailable, run
`python tests/package_smoke.py --skip-interop`; its output labels real wire tests
as skipped, not passed.
