# NWM3 messaging contract

Status: frozen contract for the NWM3 feature checkpoint; implementation follows
only after ROOT acceptance. This is maintained source, not generated site output.
The shared byte fixtures are `tests/fixtures/nwm3/wire.json` (schema version 1).
A contract change requires technical review and a new coherent checkpoint before
components adopt it; do not silently diverge in a component branch.

## Scope and compatibility

NWM3 replaces AR2 messaging and the optional NWR1 JSON/base64 application envelope
with native message metadata. It is **NWM3**, not AR3. NA1 administration, its
separate socket, credentials, persistence, configuration version 2, membership,
leases, admission, routing policy and native queue bounds remain unchanged.
There is no dual stack, negotiation, compatibility envelope, automatic retry,
reconnect, deduplication, durable storage or remote execution guarantee.

A messaging endpoint accepts only the exact version frame `NWM3`. Other versions
(including AR2) are silently dropped, without registration or routing side effects.
Clients ignore non-NWM3 responses and expire their bounded connection deadline;
they never fall back. This is the existing strict rejection style, not an immediate
`unsupported_version` receipt. Old AR2 monitoring must use its separate AR2 relay.
NA1 remains usable independently and is not a messaging negotiation mechanism.

These are breaking wire and API changes. Do not publish them as a 0.2.x patch or
alter released 0.2.x artifacts/evidence. Once implementation is authorized, use
local development versions `0.3.0.dev0` (Python) and `0.3.0-dev.0` (Node), updating
their existing lock metadata together. Those labels do not authorize a release,
tag, push, publication, installation into global Pi, or any Pi integration change.
A future public release is a separate ROOT/user decision.

## Frame notation and identifiers

Each bracketed item below is one ZeroMQ multipart frame, not JSON. Tables show
DEALER-visible frames; ROUTER prepends its opaque routing-address frame. There is
no delimiter frame. Literal command/version text is case-sensitive ASCII.

- `token`: server-created registration incarnation, 32 lowercase ASCII hex bytes;
  fence DATA and receipts against the current incarnation exactly as in AR2.
- `cid`: existing control-command correlation bytes, 1..64 bytes. HELLO, JOIN,
  LEAVE and CLOSE keep this bound; both libraries generate random 32-lowerhex cids.
- `id`: **client-created**, cryptographically random 128 bits represented by exactly
  32 lowercase ASCII hex bytes (`[0-9a-f]{32}`, full-frame match). For SEND this
  **reuses the existing command correlation position**; there is no second ID.
  The relay validates and forwards it unchanged and never creates a message ID.
- `reply_to`: zero bytes (an explicit empty frame) means absent; otherwise exactly
  the same 32-lowerhex grammar. It is not omitted, `null`, a zero byte, whitespace,
  a zero ID sentinel, or JSON. Thirty-two ASCII zeroes are a valid ID.
- `network`, `name`, `sender`, `destination`: existing strict ASCII name grammar
  `[A-Za-z0-9][A-Za-z0-9_.-]{0,127}`. No UTF-8 substitution or lossy ASCII decoding.
- `payload`: one arbitrary byte frame, including empty or invalid UTF-8. Only its
  length is interpreted. `NWR1\n...` is ordinary application payload, even when it
  contains a syntactically valid old envelope. There is no payload sniffing.

## Exact messaging frames

| Direction | Frames |
| --- | --- |
| client HELLO | `[NWM3, HELLO, cid, name]` |
| HELLO accepted | `[NWM3, OK, empty, cid, token, lease, limit, memberships]` |
| HELLO rejected | `[NWM3, ERROR, empty, cid, code]` |
| client SEND | `[NWM3, SEND, token, id, network, destination, reply_to, payload]` |
| routed DATA | `[NWM3, DATA, target_token, id, network, sender, reply_to, payload]` |
| SEND accepted | `[NWM3, OK, token, id]` |
| SEND rejected | `[NWM3, ERROR, token, id, code]` |
| client JOIN | `[NWM3, JOIN, token, cid, network, credential_or_empty]` |
| JOIN accepted | `[NWM3, OK, token, cid, network, changed]` |
| client LEAVE | `[NWM3, LEAVE, token, cid, network]` |
| LEAVE accepted | `[NWM3, OK, token, cid, network, changed]` |
| client HEARTBEAT | `[NWM3, HEARTBEAT, token]` (no receipt) |
| client CLOSE | `[NWM3, CLOSE, token, cid]` |
| CLOSE accepted | `[NWM3, OK, token, cid]` |
| other correlated rejection | `[NWM3, ERROR, token, cid, code]` |

All shapes have exact arity. `sender` comes from registration, never a client
supplied sender frame. `target_token` is the destination incarnation, not the
sender's token. Payload, ID, reply_to and selected network are forwarded exactly.
The relay may create registration tokens and control receipts, not message IDs.

HELLO `lease` keeps the existing canonical unsigned decimal grammar
`(?:0|[1-9][0-9]*)(?:\.[0-9]+)?`, 1..32 ASCII bytes, finite 0.1..3600 seconds.
`limit` is canonical positive decimal (`[1-9][0-9]*`), at most 10 bytes and
1..2147479552, specifying **payload bytes only**. Clients accept memberships only
as exact ASCII `[]` or `["default"]`, at most 32 bytes. `changed` is ASCII `0` or
`1`; JOIN/LEAVE receipts must echo the selected network. SEND/CLOSE OK have no
extra frames. HELLO's receipt token is empty even when it carries a new token.

## Validation, failures and bounds

Relay processing retains expiry-before-dispatch and incarnation fencing. Wrong
version/insufficient framing is dropped. An invalid/missing registration is
`not_registered` only if a 1..64-byte correlation frame can be safely echoed;
otherwise it is dropped. A valid registration is renewed on an authenticated
packet as before. No added request lifecycle or message-ID registry is allowed.

For an authenticated SEND, validation order is:

1. Exact SEND arity; otherwise `invalid_command` if safely correlated, else drop.
2. Required `id` grammar; otherwise `invalid_id` if 1..64 bytes, else drop.
3. `reply_to` grammar/empty representation; otherwise `invalid_reply_to`.
4. Network name, destination name, payload length, then existing network existence,
   sender membership, destination availability, destination membership and route
   policy checks, in that order.
5. Nonblocking enqueue of DATA to the target native queue; then a receipt to sender.

Thus an authenticated SEND with an empty/more-than-64-byte ID cannot be correlated
and is dropped without forwarding. A bounded malformed ID can be echoed *only in
an error receipt*, never forwarded as a valid DATA ID. Extra multipart frames must
not cause unbounded payload copying; the largest valid incoming ROUTER packet is
9 frames (address plus 8 SEND frames). A safely identifiable authenticated
oversized-arity packet is `invalid_command`. No new unbounded queue or state.
The relay need not reject equal/duplicate valid IDs or equal id/reply_to: it is
not a deduplicator. Library generation rules below prevent ID reuse for replies.

Existing relay error codes remain: `invalid_name`, `admission_denied`,
`duplicate_name`, `not_registered`, `invalid_command`, `invalid_destination`,
`invalid_network`, `network_not_found`, `join_denied`, `not_member`,
`destination_not_member`, `payload_too_large`, `route_denied`,
`destination_unavailable`, `destination_full`, `unsupported_version`. Add only
`invalid_id` and `invalid_reply_to`. `unsupported_version` remains recognized,
not a promise of a reply to an unknown wire version.

The configured payload limit remains 1..2147479552 (default 1048576); it excludes
metadata and has no NWR1/base64 overhead. Payload exactly at limit is allowed;
limit+1 is rejected. Keep native MAXMSGSIZE at payload limit+4096 and existing
message-count HWMs, inbox and pending caps. Native transport may discard packets
above its ceiling before application rejection can be emitted. No claim is made
that metadata/native buffers count against the payload limit or a total-byte cap.

Clients discard malformed DATA (wrong arity, version, token, ID, reply_to, names or
payload limit); they must not turn it into an ordinary application message.
Valid DATA that does not match an active app waiter goes to the ordinary inbox.
Unmatched/stale receipts are ignored. A malformed receipt matching current token
and pending command ID fails that operation with `invalid_receipt`; recognized
relay ERRORs retain typed codes. Local invalid metadata is rejected before write.

## Acceptance and request lifecycle

`send()` resolves to its generated ID **only after** a correctly correlated empty
SEND OK. It means the relay accepted DATA into the target native queue, not remote
receipt, processing, execution, delivery durability or application success. A
successful `reply()` has precisely the same meaning and returns the new reply ID.
Lost/full sender receipt delivery does not undo already queued DATA.

Every send creates a fresh random ID, including every reply. No public caller-
supplied `id` option is introduced. Never copy the incoming ID as a reply's own ID;
put it in reply_to instead. A reply ID must differ from its referenced ID. Avoid
collisions with the library's currently outstanding IDs; do not create a durable
ID registry. No ordering/deduplication promise follows from ID uniqueness.

`request()` creates its ID and installs a bounded waiter **before any send/await**,
then sends one ordinary SEND with empty reply_to. There is no request kind/flag
and no broker request state. Its one finite positive overall deadline covers send
acceptance and waiting, not separate full deadlines. The sole reader must match
all three: incoming `reply_to == request.id`, expected sender == destination,
and expected network == selected network. The incoming reply also has a valid,
independent ID. Correlation by ephemeral labels is not authenticated identity.

Preserve existing first-terminal-event semantics: a reader-accepted matching reply
can complete request before/without SEND OK. A SEND rejection/local failure,
receipt failure, cancellation, deadline or close that wins first removes the app
waiter. Settle ownership synchronously at the native reader/local terminal event,
not later in a task/Promise callback that another DATA can overtake. Caller cancel
must not discard a reply already owned by that waiter. Cancel only operation-owned
children/waits, not the shared reader/socket or another operation.

Return the **whole native Message**, with raw reply payload, own ID and reply_to;
no encode/decode step. Request completion is evidence of a matching reply, not a
claim of durable business completion. Timeout remains `ReceiptTimeout`; Python
uses task cancellation, Node uses the existing AbortSignal/reason contract.
Timeout/cancel/lifecycle interruption after write has uncertain effects and never
retries. A late reply, duplicate reply, wrong-sender/network reply, unsolicited
reply, or valid NWR1-looking payload remains ordinary inbox data. No hidden stash.
A full ordinary inbox pauses the sole reader and can stall receipt/reply progress;
applications must drain it concurrently. Existing independent control/app waiter
caps, cleanup guarantees and queued-after-close reading remain intact.

## Public API and export changes

Python (async):

```python
@dataclass(frozen=True)
class Message:
    id: str
    sender: str
    network: str
    payload: bytes
    reply_to: str | None = None

async def send(destination: str, payload: bytes, *, network="default",
               reply_to: str | None = None, timeout=None) -> str: ...
async def request(destination: str, payload: bytes, *, network="default",
                  timeout=None) -> Message: ...
async def reply(incoming: Message, payload: bytes, *, timeout=None) -> str: ...
```

Use keyword construction for synthetic Messages; the displayed dataclass field
order is normative. No legacy missing-ID constructor. `None` is the only absent
Python reply_to, not empty string. `reply()` validates Message metadata, targets
incoming.sender/network and sets reply_to=incoming.id. It may reply to **any**
valid Message, including a reply; there is no request-envelope/kind requirement.
No reply network override. All public byte type checks and timeout bounds remain.

Node/TypeScript (ESM):

```typescript
interface Message {
  readonly id: string;
  readonly sender: string;
  readonly network: string;
  readonly payload: Uint8Array;
  readonly reply_to: string | undefined;
}
interface RequestOptions extends OperationOptions { network?: string; }
interface SendOptions extends RequestOptions { reply_to?: string; }
send(destination: string, payload: Uint8Array, options?: SendOptions): Promise<string>;
request(destination: string, payload: Uint8Array, options?: RequestOptions): Promise<Message>;
reply(incoming: Message, payload: Uint8Array, options?: OperationOptions): Promise<string>;
```

Keep metadata spelling `reply_to` in both languages and CLI, with no alias.
Node received Message always has a reply_to property (undefined when absent).
Omitted/undefined is absent on send; null/empty-string/malformed IDs are invalid.
Snapshot payload and incoming reply metadata before the first await, retaining
existing ownership/mutation safety. Request does not accept a reply_to override;
reply rejects a runtime network/reply_to/id override. Export RequestOptions along
with the existing useful Node types. Do not expose a public ID injection API;
an internal explicit-ID send/control path may support preinstalled app waiters.

Delete both envelope implementation files and their dedicated tests. Remove
Envelope, encode_envelope/decode_envelope and encodeEnvelope/decodeEnvelope exports
from Python root/client/python and Node entry points; no compatibility shim,
parallel parser or deprecated envelope helper. Preserve Node, Message,
MembershipReceipt, errors, administration and configuration exports. Update
relevant callers, tests, examples and maintained docs to use native metadata.

## CLI JSON and migration

Keep bounded one-shot send/receive/request/reply commands, stdin/file **raw bytes**
and existing limits, finite waits, membership and cleanup behavior. CLI base64
remains only a JSON I/O representation; it is not a wire/application envelope.
Do not add a persistent client mode, manual ID flag or generic controller.

Every message event, including unrelated messages during request, is exactly:

```json
{"event":"message","id":"11111111111111111111111111111111","reply_to":null,"network":"default","sender":"alpha","payload":"AP8="}
```

Terminal request result uses the same fields with `event:"reply"`; its id is the
reply's ID and reply_to is the request's ID. A missing correlation is explicit
JSON null, not an omitted key or empty string. Send/reply accepted events are:

```json
{"event":"accepted","id":"22222222222222222222222222222222","reply_to":"11111111111111111111111111111111","network":"default","recipient":"alpha","meaning":"native_queue_acceptance_only"}
```

Ordinary send uses reply_to:null; reply uses the incoming ID. Emit only after
queue acceptance. Existing ready/complete and administrative events are unchanged.
A request need not emit a separate accepted event; its terminal reply exposes
both IDs. JSON key ordering is not semantic; output remains one compact object
per line with existing byte/count budgets.

`reply --request-file` accepts exactly the six keys of a `message` event above:
strict unique keys, event==message, valid id, reply_to null or a valid ID, valid
names, canonical base64 string decoding to bounded bytes. Reject missing/unknown
fields, old four-field events, duplicate keys, malformed/oversized metadata,
noncanonical base64, nonfinite JSON and wrong types before connecting/sending.
Construct the native Message and reply to its id; no NWR1 decoding. A prior reply
in a receive message event is valid input. event==reply remains invalid input.

Migration is explicit: reconnect all messaging clients to a matching NWM3 relay;
remove envelope imports and decoding; access Message.payload directly; use
Message.id and Message.reply_to for application correlation; consume returned
send/reply IDs; regenerate saved CLI receive events in the new six-key format.
Never auto-detect or translate old envelope bytes or metadata. Keep no-effect vs
indeterminate CLI errors and release-after-result semantics unchanged.

## Shared fixtures and implementation acceptance

`wire.json` encodes exact frames as objects containing one `ascii` or `hex` key.
ASCII must be strict 7-bit; hex must be lowercase even-length hex. Empty frames
are `{ "hex": "" }`. No transport address is part of a fixture's frames.
It supplies exact control packets, successful SEND/DATA/receipt pairs, metadata
rejections, malformed DATA and CLI events. Fixture context declares registration
names/tokens/membership and a small payload limit; harnesses set it up, not infer
credentials or start any shared/global relay. Dynamic test IDs may use the same
valid grammar; random generation is checked separately, not against fixed IDs.

Both client owners must consume the same committed fixtures in their tests.
Fixtures are not proof of implementation: relay round trips, fake-router client
validation/races, cross-language binary interop, CLI bounds/correlation, malformed
wire/version rejection and unchanged NA1 behavior must be tested in component
and assembled-candidate checks. Independent black-box verification starts from
the integrated candidate, not a divergent component snapshot. No generated
root `docs/` files belong in these commits.
