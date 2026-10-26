import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import {
  Node,
  ReceiptTimeout,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";
import {
  fakeRelay,
  TOKEN,
} from "../../../../helpers/nodalwire/client/node/fake-relay.mjs";

const status = (code) => (error) => error instanceof RelayError && error.code === code;

test("HELLO reader fences immediate DATA before connect continuation", {
  timeout: 3000,
}, async () => {
  const relay = await fakeRelay(async (peer) => {
    if (peer.command !== "HELLO") return;
    await peer.ok(TOKEN, "10", "1024", "[]");
    await peer.data("team", "peer", Uint8Array.of(42));
    return true;
  });
  const node = await Node.connect("node", relay.endpoint);
  try {
    assert.deepEqual(await node.receive({ signal: AbortSignal.timeout(1000) }), {
      network: "team",
      sender: "peer",
      payload: Uint8Array.of(42),
    });
  } finally {
    await node.close();
    await relay.close();
  }
});

test(
  "pre-aborted membership/request operations emit no frames; failed control allocation releases app slot",
  { timeout: 3000 },
  async () => {
    const relay = await fakeRelay((peer) => peer.command === "SEND");
    const node = await Node.connect("node", relay.endpoint, {
      maxPending: 1,
      timeout: 0.04,
    });
    try {
      const controller = new AbortController();
      controller.abort(new Error("fixture cancellation"));
      for (
        const invoke of [
          () => node.join("team", undefined, { signal: controller.signal }),
          () => node.leave("team", { signal: controller.signal }),
          () => node.request("peer", new Uint8Array(), { signal: controller.signal }),
        ]
      ) await assert.rejects(invoke(), { message: "fixture cancellation" });
      assert.equal(relay.seen.length, 1);
      const occupied = assert.rejects(
        node.send("peer", new Uint8Array()),
        ReceiptTimeout,
      );
      // App slot is free but the independent control-receipt slot is occupied.
      await assert.rejects(
        node.request("peer", new Uint8Array()),
        status("pending_full"),
      );
      await occupied;
      // The preceding failed request must not retain its app registration.
      await assert.rejects(node.request("peer", new Uint8Array()), ReceiptTimeout);
      assert.equal(
        relay.seen.filter((frames) => frames[2].toString() === "SEND").length,
        2,
      );
      await node.join("team");
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "concurrent app requests do not create an outbound queue; cleanup permits later requests",
  { timeout: 3000 },
  async () => {
    const relay = await fakeRelay((peer) => peer.command === "SEND");
    const node = await Node.connect("node", relay.endpoint, {
      maxPending: 2,
      timeout: 0.04,
    });
    try {
      const first = assert.rejects(
        node.request("peer", Uint8Array.of(1)),
        ReceiptTimeout,
      );
      await assert.rejects(
        node.request("peer", Uint8Array.of(2)),
        status("local_queue_full"),
      );
      await first;
      await assert.rejects(node.request("peer", Uint8Array.of(3)), ReceiptTimeout);
      const sends = relay.seen.filter((frames) => frames[2].toString() === "SEND");
      assert.equal(sends.length, 2, "rejected native write was not queued or replayed");
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "canceling join leaves one reader alive and no automatic retry",
  { timeout: 3000 },
  async () => {
    const relay = await fakeRelay((peer) => peer.command === "JOIN");
    const node = await Node.connect("node", relay.endpoint);
    try {
      const controller = new AbortController();
      const canceled = assert.rejects(
        node.join("team", "fixture-token", { signal: controller.signal }),
        { name: "AbortError" },
      );
      await sleep(10);
      controller.abort();
      await canceled;
      const peer = relay.peers.get("node");
      await peer.data("team", "peer", Uint8Array.of(99));
      assert.equal(
        (await node.receive({ signal: AbortSignal.timeout(1000) })).payload[0],
        99,
      );
      assert.equal(
        relay.seen.filter((frames) => frames[2].toString() === "JOIN").length,
        1,
      );
    } finally {
      await node.close();
      await relay.close();
    }
  },
);
