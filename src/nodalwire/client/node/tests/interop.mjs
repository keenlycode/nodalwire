import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import process from "node:process";
import { setTimeout as sleep } from "node:timers/promises";
const { Node, ReceiptTimeout, RelayError } = await import(
  process.env.NODALWIRE_CLIENT_MODULE ?? "../dist/index.js"
);

const endpoint = process.argv[2];
const status = (code) => (error) => error instanceof RelayError && error.code === code;
const boundedReceive = (node) => node.receive({ signal: AbortSignal.timeout(1000) });
const alice = await Node.connect("js-node", endpoint);
try {
  for (
    const payload of [
      Uint8Array.from({ length: 256 }, (_, i) => i),
      Buffer.alloc(0),
      Uint8Array.of(99, 0, 255, 88).subarray(1, 3),
    ]
  ) {
    const snapshot = Uint8Array.from(payload);
    const sent = alice.send("py-echo", payload);
    payload.fill(42); // API snapshots synchronously, including a subarray's bounds.
    await sent;
    const message = await boundedReceive(alice);
    assert.equal(message.sender, "py-echo");
    assert.deepEqual(message.payload, snapshot);
  }
  await assert.rejects(
    alice.send("missing", new Uint8Array()),
    status("destination_unavailable"),
  );
  await assert.rejects(
    alice.send("py-denied", new Uint8Array()),
    status("route_denied"),
  );
  await assert.rejects(
    alice.send("py-echo", new Uint8Array(1025)),
    status("payload_too_large"),
  );
  await assert.rejects(Node.connect("js-node", endpoint), status("duplicate_name"));
  await sleep(1050); // > 3 lease periods, application-idle heartbeat maintenance.
  await assert.rejects(Node.connect("js-node", endpoint), status("duplicate_name"));
  await alice.send("py-echo", Uint8Array.of(1));
  assert.deepEqual((await boundedReceive(alice)).payload, Uint8Array.of(1));

  const cancelled = new AbortController();
  const waiting = alice.receive({ signal: cancelled.signal });
  cancelled.abort();
  await assert.rejects(waiting, { name: "AbortError" });
  await alice.send("py-echo", Uint8Array.of(2));
  assert.deepEqual((await boundedReceive(alice)).payload, Uint8Array.of(2));
} finally {
  await alice.close();
}
await assert.rejects(alice.receive(), status("closed"));
const replacement = await Node.connect("js-node", endpoint);
await Promise.all([replacement.close(), replacement.close()]);
await replacement.close();
console.log(
  "PASS admission, receipts, byte snapshots, heartbeat, canceled waiter and clean release",
);

// One bounded inbox plus one held DATA pauses all subsequent native receipts.
const source = await Node.connect("source", endpoint);
const busy = await Node.connect("busy", endpoint, {
  inboxSize: 1,
  maxPending: 1,
  timeout: 0.15,
});
try {
  await source.send("busy", Uint8Array.of(10));
  await source.send("busy", Uint8Array.of(11));
  await sleep(30);
  const uncertain = busy.send("source", Uint8Array.of(12));
  const rejected = busy.send("source", Uint8Array.of(13));
  await assert.rejects(rejected, status("pending_full"));
  assert.deepEqual((await boundedReceive(source)).payload, Uint8Array.of(12));
  await assert.rejects(uncertain, ReceiptTimeout); // Forwarded before receipt timeout.
  assert.deepEqual((await boundedReceive(busy)).payload, Uint8Array.of(10));
  assert.deepEqual((await boundedReceive(busy)).payload, Uint8Array.of(11));
  await busy.send("source", Uint8Array.of(14)); // Timed-out correlation was removed.
  assert.deepEqual((await boundedReceive(source)).payload, Uint8Array.of(14));
  await source.send("busy", Uint8Array.of(15));
  await sleep(30);
  await busy.close();
  assert.deepEqual((await busy.receive()).payload, Uint8Array.of(15));
  await assert.rejects(busy.receive(), status("closed"));
} finally {
  await Promise.all([busy.close(), source.close()]);
}
console.log(
  "PASS bounded inbox/pending, honest after-effect timeout, receive-after-close",
);

const closerSource = await Node.connect("closer-source", endpoint);
const closer = await Node.connect("closer", endpoint, { inboxSize: 1 });
try {
  await closerSource.send("closer", Uint8Array.of(20));
  await closerSource.send("closer", Uint8Array.of(21));
  await sleep(30);
  const close = closer.close({ signal: AbortSignal.timeout(40) });
  const joined = closer.close();
  await assert.rejects(close, { name: "TimeoutError" });
  await joined;
  await closer.close();
  await assert.rejects(
    closer.send("closer-source", new Uint8Array()),
    status("closed"),
  );
} finally {
  await Promise.all([closer.close(), closerSource.close()]);
}
console.log("PASS canceled blocked close with shared completing cleanup");
