# NodalWire Node client

TypeScript byte client for the existing **trusted local** Python NodalWire relay.
Node.js 24 only; verified on Node 24.15.0, Linux x64/glibc. Deno orchestrates
development; **Deno runtime execution is not supported**. ESM only, no CommonJS.
No authentication, encryption, RPC, encoding helpers, retries or replay.

## Use

Install the client in your application (the native `zeromq` install script is needed):

```sh
npm install @devcapsule/nodalwire-client
```

To build and pack a local checkout instead:

```sh
cd src/nodalwire/client/node
pnpm install --frozen-lockfile --store-dir ./node_modules/.pnpm-store
deno task build
pnpm pack
# In your application:
pnpm add /absolute/path/to/devcapsule-nodalwire-client-0.1.0.tgz
```

For pnpm versions requiring script approval, allow **only `zeromq`** in the
application's `pnpm-workspace.yaml` (`allowBuilds: { zeromq: true }`). This checkout
already includes that approval. Native prebuilt availability/platform requirements
belong to zeromq; other platforms and Node versions have not been verified.

```ts
import { Node } from "@devcapsule/nodalwire-client";

const alice = await Node.connect("alice", "tcp://127.0.0.1:5555");
try {
  await alice.send("bob", Uint8Array.of(0, 255, 128));
  const { sender, payload } = await alice.receive();
  console.log(sender, payload);
} finally {
  await alice.close();
}
```

Start the Python relay separately with `nodalwire`.
Connect waits for admission, validates the same logical names and loopback TCP
endpoints, and normalizes `localhost` without DNS. The logical name is distinct
from the random native routing ID. Admission tokens fence each incarnation.

## Contract

- `Node.connect(name, endpoint?, options?) -> Promise<Node>`
- `send(destination, payload: Uint8Array, options?) -> Promise<void>`;
  `Buffer` works naturally. Outgoing bytes are **copied synchronously**, including
  subarray bounds: mutation after calling send does not change the packet.
- `receive({ signal? }?) -> Promise<Message>` with `sender` and caller-owned,
  mutable `payload: Uint8Array`. There is one ordered bounded inbox/native reader.
- `close({ timeout?, signal? }?) -> Promise<void>` attempts registration release,
  then always closes the socket and joins its reader/writer. Aborting close does
  not abort cleanup. Concurrent/repeated close waits for cleanup, without repeating
  the release request. Only the first close caller controls the release timeout/
  signal; later close waits are not independently cancelable. A canceled/timed-out
  release may persist until lease expiry.

Options use camelCase: `timeout=5` **seconds** (also per-send/per-close),
`sendHwm=64`, `receiveHwm=64`, `inboxSize=64`, `maxPending=128`, and optional
`signal: AbortSignal`. Positive finite timeouts must fit a native timer; queue
limits must be positive native integers. Receive supports cancellation, not a
separate receipt timeout; use an AbortSignal for a bounded wait.

Success means **Router acceptance into the destination's native socket queue**,
not remote receipt, execution or durability. `RelayError.code` mirrors Python:
`destination_full`, `destination_unavailable`, `route_denied`,
`payload_too_large`, `invalid_destination`, admission/protocol codes, and local
`pending_full`, `local_queue_full`, `closed`, `connection_failed`.
`ReceiptTimeout` explicitly states **effect uncertain**. AbortSignal rejection
uses the signal's reason. Timeout, cancellation or lifecycle interruption can
happen **after forwarding**; never infer non-delivery or retry blindly.

The inbox retains queued data after close; an empty closed inbox rejects `closed`
and wakes waiting consumers. Canceling receive removes only that waiter, never
abandons the single native receive. When the inbox is full, one DATA can wait for
space and the native reader pauses **including control receipts**. Drain receive
concurrently with sending; otherwise even your send/close receipts may time out.
Heartbeats run every lease/3, without a backlog, and may be skipped under pressure.

### Deliberate native differences / limits

There is no JavaScript outbound backlog. If another native send is still in
flight, send rejects `local_queue_full` even if the native HWM is not yet full;
this differs from Python's nonblocking send scheduling. Receipt concurrency is
allowed once each native write settles, bounded by `maxPending`. HWM counts
messages per peer, not total bytes; kernel buffers also contribute. The admitted
payload cap is enforced in the client, but no post-admission native MAXMSGSIZE
claim is made. Zeromq does not expose Python's explicit context termination;
cleanup closes owned sockets and joins their operations, not a global context.

Only targeted normal functionality/lifecycle has been verified. No security,
fuzz, stress, adversarial, production-hardening, older-Node, other-platform or
Deno-runtime support is claimed. The relay/protocol implementation is unchanged.

## Development

Requires local pnpm dependencies, Node 24, Deno (verified 2.7.14), and Python with
PyZMQ (verified Python 3.14.7 / PyZMQ 27.1.0). From this directory:

```sh
deno task fmt
deno task lint
deno task check
deno task build
deno task test
python tests/package_smoke.py
```

Deno type-checks only; `--sloppy-imports` maps source `.js` imports to TypeScript.
Local TypeScript 5.9.3 emits ESM JS and declarations into `dist/`. All native tests
run explicitly with Node, never Deno. Python integration starts/cleans its own
loopback relay and echo client; it imports this checkout's Python `src/` without
modification. Test subprocesses and per-test waits are bounded. Package smoke
uses the local dependency store (override `NODALWIRE_PNPM_STORE` if needed),
installs an actual tarball, checks declarations and reruns real interoperability.
