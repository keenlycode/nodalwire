# NodalWire

`nodalwire` is a small central native ZeroMQ byte relay. One service owns a
ROUTER socket; each Python node owns one DEALER connection to it. This is for trusted applications on the
same host only: no authentication or encryption is provided. Any trusted local
process may connect; names are logical labels, not cryptographically authenticated
principals. Admission and routing policy are cooperative, not a security boundary.
There is no untrusted-client or production-network support.

Applications choose their own byte encoding and request/reply meanings. No JSON
helpers, RPC, browser operations, PUB/SUB, direct peer connections, persistence,
retries or replay are provided.

## Run

Requires Python 3.12 or newer. PyZMQ and Cyclopts are normal dependencies.
Install the package into your own environment with `pip install .`, or prepare
this checkout with `uv sync --locked`. Starting the relay installs nothing.

```sh
# Installed entry point; equivalent to python -m nodalwire:
nodalwire
# In another terminal, using the same environment:
python -m nodalwire.examples.two_nodes
```

The example prints the actual sender and binary payloads in both directions.
Both example definitions ship inside the wheel and sdist, without duplicate
checkout-only copies. To use or edit the shipped cooperative policy:

```sh
python -c 'from importlib.resources import files; print(files("nodalwire").joinpath("examples/local.toml").read_text(), end="")' > local.toml
nodalwire --config local.toml
```

From a prepared source checkout, `uv run --locked nodalwire --config
src/nodalwire/examples/local.toml` uses that same policy definition. No previous
project, external scratch directory or task record is required.

Without a config file the bind is `tcp://127.0.0.1:5555`, admission is open,
leases are 10 seconds, both native high-water marks are 64 messages, and the
payload limit is 1 MiB. The foreground service prints its bound endpoint after
startup. SIGINT/SIGTERM closes its tasks, sockets and context.
Policy is loaded once; there is no admin API or hot reload.

Both bind and client connect endpoints must be loopback-only TCP: literal
loopback IPv4, bracketed `::1`, or `localhost` (normalized to `127.0.0.1`
without DNS resolution). Wildcard/nonlocal hosts and other hostnames are rejected
before allocating transport resources. `tcp://127.0.0.1:*` selects an available
bind port; connects require a numeric port. There is no nonlocal opt-in.
Unsupported `curve` and `allow_nonlocal` TOML settings are rejected explicitly,
including `allow_nonlocal = false`; the Python API has no such options.
NodalWire makes no secure-networking claim.

## Async Python API

```python
import asyncio
from nodalwire import Node

async def application():
    alice = await Node.connect("alice", "tcp://127.0.0.1:5555")
    try:
        await alice.send("bob", b"opaque\x00\xff")
        incoming = await alice.receive()
        print(incoming.sender, incoming.payload)
    finally:
        await alice.close()

asyncio.run(application())
```

Each node has one logical inbox of `Message(sender: str, payload: bytes)`.
Names are ASCII letters/digits followed by letters/digits/`_`/`.`/`-`, at most
128 characters. Payloads must be `bytes`; empty and arbitrary binary bytes are
preserved. The actual sender comes from the admitted transport registration,
not a field inside application data. The logical name is not the native random
routing address. `await Node.connect(...)` waits for Router admission before it
returns. Connect failure always closes that attempt's resources.

`await node.send(destination, payload)` waits for Router handing that payload
to the destination's native socket queue, or a failure status. Success is **not**
remote receipt, execution, durability, or proof that the destination is reading.
The peer may disappear after queue acceptance. A missing receipt can occur
**after forwarding**. There are no transparent retries or reconnects.

- `RelayError.code`: `destination_full`, `destination_unavailable`,
  `route_denied`, `payload_too_large`, `invalid_destination` and protocol
  rejections mean this request was not forwarded by the Router.
- Local `pending_full`, `local_queue_full`, and local validation failures occur
  before that request is accepted for relay processing.
- `ReceiptTimeout`, task cancellation, and `closed`/`connection_failed` when
  they interrupt an outstanding request have **uncertain effects**. Lifecycle
  error codes alone do not prove non-delivery. Decide recovery at the application
  level; do not blindly retry non-idempotent operations.

Close attempts registration release and waits for its receipt, then always
cancels heartbeat/receiver tasks and closes the socket/context, even if it fails
or is canceled during task cleanup. A close timeout/cancellation does not prove
release; a live registration can remain until expiry. Repeated/concurrent close
waits for native cleanup completion. Queued inbox entries remain readable after
close; an empty closed inbox raises `RelayError("closed")` and wakes waiters.

Client options: `timeout=5.0`, `send_hwm=64`, `receive_hwm=64`, `inbox_size=64`,
`max_pending=128`. Per-send and per-close
`timeout=` overrides are available. Construct clients with `Node.connect`, not
the lower-level initializer. A node and its tasks belong to one asyncio loop.

### Pressure is bounded, not reliable delivery

The Router uses `ROUTER_MANDATORY` plus nonblocking `DONTWAIT`. Missing/full
native destination routes fail explicitly; there is no Python outbound queue.
One busy destination does not block other destinations. Native HWM limits are
per pipe and count messages, not bytes; OS TCP buffering also contributes.
The configured payload cap bounds accepted message size. Grossly oversized raw
wire messages can be disconnected by native `MAXMSGSIZE` without a receipt.

The client inbox is bounded. When full, one in-flight DATA packet waits for
space and the ordered DEALER reader pauses, including later control receipts.
Thus a node that does not drain its inbox may time out its own sends or close
**after their effect**. Heartbeats run separately on the outbound socket, but
can be skipped if that native queue is full. Drain the inbox concurrently with
sending in long-lived applications. Correlation storage is capped by
`max_pending`; completed/timed-out/canceled requests are removed. No hidden
unbounded inbox, control backlog or replay storage is introduced.

## Admission, networks and leases

See [`src/nodalwire/examples/local.toml`](src/nodalwire/examples/local.toml). `allowed_names` is optional;
omitting it permits any valid name, while an empty array denies all names.
Networks are Router-configured member lists; clients cannot self-claim groups.
Routing permits by default, except directional entries in `deny`. Each entry
is `[source_selector, destination_selector]`; selectors are exact names,
`@network`, or `*`. A matching deny always wins, including within a network.
There is no implicit same-network-only rule or separate permit rule language.

An active duplicate logical name is rejected. Clean close releases it. Automatic
heartbeats every lease/3 and valid token-bearing activity maintain its lease.
A crash does not immediately release the name: a fresh client waits for the
configured lease to expire, with no takeover. Expiry is logical, not immediate
TCP-loss detection. Expiry is checked before incoming messages can refresh it.
Each registration gets a new incarnation identifier (a lifecycle fence, not an
authentication token or access credential); stale SEND,
HEARTBEAT and CLOSE frames cannot change a later registration even when the
same native routing address is reused. Already accepted payloads are not recalled.

## Embedded service and wire boundary

Import `Relay` and `RelayConfig` from `nodalwire`.
`relay = Relay(RelayConfig(...))`; `await relay.start()` returns the actual
endpoint. Run `relay.run()` in a task, cancel and await it before
`await relay.close()`. The relay owns its context and native socket.
Use a dedicated relay instance per context/service.

Private wire version `AR1` begins every multipart message. DEALER sends these
frames (the ROUTER additionally sees the native routing-address envelope):

| Command | Remaining frames |
| --- | --- |
| HELLO | request-id, logical-name |
| SEND | token, request-id, destination-name, opaque-payload |
| HEARTBEAT | token |
| CLOSE | token, request-id |

Router replies: `OK, empty-token, request-id, new-token, lease-seconds,
max-payload-bytes` for HELLO; `OK, token, request-id` for SEND/CLOSE;
`ERROR, token, request-id, code` for rejection (empty token for HELLO).
Forwarded DATA: `DATA, destination-token, admitted-sender-name, opaque-payload`.
All are prefixed by `AR1`. Request IDs are helper-owned, not an application
payload schema. Destination tokens fence unread old-incarnation data.

## Verification

Unit checks live in `tests/unit/`; native integration checks live in
`tests/integration/`. They cover real TCP sockets and separate service/application
processes, byte transparency, policy, leases, stale tokens, native HWM pressure,
bounded client bookkeeping, uncertain receipts, deterministic cancellation-safe
cleanup, local endpoint validation and unsupported configuration errors.
Prepare this checkout's dev environment with `uv sync --locked`, then run:

```sh
uv run --locked pytest -q
uv run --locked ruff check src tests
uv lock --offline --check
uv build
```

The maintained `uv.lock` is a genuine uv-generated standalone lock. Offline
commands require the selected dependencies already to be cached; offline is not
a promise of installation on a fresh machine.

These checks do not establish arbitrary-network performance, production safety,
exactly-once/durable delivery, immediate loss detection or application correctness.
