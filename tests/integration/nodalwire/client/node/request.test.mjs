import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import {
  decodeEnvelope,
  encodeEnvelope,
  Node,
  ReceiptTimeout,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";
import { fakeRelay } from "../../../../helpers/nodalwire/client/node/fake-relay.mjs";

const status = (code) => (error) => error instanceof RelayError && error.code === code;
const bounded = () => ({ signal: AbortSignal.timeout(1000) });
const envelope = (kind, id, payload = Uint8Array.of(255, 0)) =>
  encodeEnvelope({ kind, id, payload });

test(
  "request correlates expected network/sender/kind/id without discarding unrelated DATA",
  { timeout: 3000 },
  async () => {
    const unrelated = [];
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      const request = decodeEnvelope(peer.frames[7]);
      const cases = [
        ["team", "peer", Uint8Array.of(9)],
        ["wrong", "peer", envelope("reply", request.id)],
        ["team", "wrong", envelope("reply", request.id)],
        ["team", "peer", envelope("request", request.id)],
        ["team", "peer", envelope("reply", "0".repeat(32))],
        ["team", "peer", Buffer.from('NWR1\n{"malformed":true}')],
      ];
      for (const [network, sender, payload] of cases) {
        unrelated.push({ network, sender, payload: Uint8Array.from(payload) });
        await peer.data(network, sender, payload);
      }
      // App reply BEFORE routing receipt; request must not silently lose it.
      await peer.data("team", "peer", envelope("reply", request.id));
      await peer.ok();
      await peer.data("team", "peer", Uint8Array.of(10));
      return true;
    });
    const node = await Node.connect("node", relay.endpoint);
    try {
      const waiting = node.receive(bounded());
      const result = await node.request("peer", Uint8Array.of(1), { network: "team" });
      assert.deepEqual(result, {
        network: "team",
        sender: "peer",
        payload: Uint8Array.of(255, 0),
      });
      assert.deepEqual(await waiting, unrelated[0]);
      for (const expected of unrelated.slice(1)) {
        assert.deepEqual(
          await node.receive(bounded()),
          expected,
        );
      }
      assert.equal((await node.receive(bounded())).payload[0], 10);
      assert.equal(node.receiveNowait(), undefined);
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "matching reply wins missing/negative SEND receipt; own receipt wait never leaks pending capacity",
  { timeout: 3000 },
  async () => {
    let sequence = 0;
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      const request = decodeEnvelope(peer.frames[7]);
      sequence++;
      await peer.data(
        "default",
        "peer",
        envelope("reply", request.id, request.payload),
      );
      if (sequence % 2 === 0) await peer.error("destination_unavailable");
      return true;
    });
    const node = await Node.connect("node", relay.endpoint, {
      maxPending: 1,
      timeout: 0.04,
    });
    try {
      for (
        const payload of [
          new Uint8Array(),
          Uint8Array.of(1),
          Uint8Array.of(2),
          Uint8Array.of(3),
        ]
      ) {
        const result = await node.request("peer", payload);
        assert.deepEqual(result.payload, payload);
      }
      assert.equal(node.receiveNowait(), undefined);
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "SEND rejection/timeout/abort unregisters first; subsequent replies are ordinary messages",
  { timeout: 3000 },
  async () => {
    let mode = "reject";
    const received = [];
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      const request = decodeEnvelope(peer.frames[7]);
      received.push({ peer, request });
      if (mode === "reject") await peer.error("destination_unavailable");
      else if (mode === "accept") await peer.ok();
      return true;
    });
    const node = await Node.connect("node", relay.endpoint, { timeout: 0.04 });
    try {
      await assert.rejects(
        node.request("peer", new Uint8Array()),
        status("destination_unavailable"),
      );
      mode = "silent";
      await assert.rejects(node.request("peer", new Uint8Array()), ReceiptTimeout);
      mode = "accept";
      await assert.rejects(node.request("peer", new Uint8Array()), ReceiptTimeout);
      const controller = new AbortController();
      const canceled = assert.rejects(
        node.request("peer", new Uint8Array(), { signal: controller.signal }),
        { name: "AbortError" },
      );
      await sleep(10);
      controller.abort();
      await canceled;
      for (const { peer, request } of received) {
        const late = envelope("reply", request.id);
        await peer.data("default", "peer", late);
        assert.deepEqual(
          (await node.receive(bounded())).payload,
          Uint8Array.from(late),
        );
      }
      assert.equal(received.length, 4);
      assert.equal(
        relay.seen.filter((frames) => frames[2].toString() === "SEND").length,
        4,
        "no retry/replay",
      );
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "one overall request deadline includes receipt wait; reply after deadline remains readable",
  { timeout: 3000 },
  async () => {
    let sent;
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      sent = { peer, request: decodeEnvelope(peer.frames[7]) };
      await sleep(55);
      await peer.ok();
      return true;
    });
    const node = await Node.connect("node", relay.endpoint);
    try {
      const start = performance.now();
      await assert.rejects(
        node.request("peer", new Uint8Array(), { timeout: 0.08 }),
        ReceiptTimeout,
      );
      assert.ok(
        performance.now() - start < 125,
        "not a new full deadline after SEND receipt",
      );
      const late = envelope("reply", sent.request.id);
      await sent.peer.data("default", "peer", late);
      assert.deepEqual((await node.receive(bounded())).payload, Uint8Array.from(late));
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "app waiter cap is independent; canceled/closed waiters release capacity and drain no native DATA",
  { timeout: 3000 },
  async () => {
    const relay = await fakeRelay(async (peer) => {
      if (peer.command === "SEND") {
        await peer.ok();
        await peer.data("default", "other", Uint8Array.of(9));
        return true;
      }
    });
    const node = await Node.connect("node", relay.endpoint, { maxPending: 1 });
    try {
      const first = assert.rejects(
        node.request("peer", Uint8Array.of(1)),
        status("closed"),
      );
      // FIFO DATA after OK proves the client reader consumed the receipt.
      assert.equal((await node.receive(bounded())).payload[0], 9);
      await assert.rejects(
        node.request("peer", Uint8Array.of(2)),
        status("pending_full"),
      );
      // A separate receipt remains usable while the app waiter slot is occupied.
      await node.join("team");
      await node.close();
      await first;
      assert.equal(node.receiveNowait(), undefined);
      await assert.rejects(node.request("peer", new Uint8Array()), status("closed"));
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "reply requires request envelope and fixes incoming network; snapshots caller bytes",
  { timeout: 3000 },
  async () => {
    const relay = await fakeRelay();
    const node = await Node.connect("node", relay.endpoint);
    try {
      const id = "a".repeat(32);
      const incoming = {
        network: "team",
        sender: "peer",
        payload: envelope("request", id),
      };
      const payload = Uint8Array.of(1, 2);
      const sent = node.reply(incoming, payload);
      payload.fill(0);
      incoming.payload.fill(0);
      incoming.network = "mutated";
      await sent;
      const frames = relay.seen.find((frames) => frames[2].toString() === "SEND");
      assert.equal(frames[5].toString(), "team");
      assert.deepEqual(decodeEnvelope(frames[7]), {
        kind: "reply",
        id,
        payload: Uint8Array.of(1, 2),
      });
      for (const payload of [new Uint8Array(), envelope("reply", id)]) {
        await assert.rejects(
          node.reply({ network: "team", sender: "peer", payload }, Uint8Array.of(1)),
          TypeError,
        );
      }
      await assert.rejects(
        node.reply(
          { network: "team", sender: "peer", payload: envelope("request", id) },
          new Uint8Array(),
          { network: "wrong" },
        ),
        TypeError,
      );
      await assert.rejects(
        node.request("peer", new Uint8Array(1048576)),
        status("payload_too_large"),
      );
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "request full-inbox pressure causes honest timeout without dropping wanted or unrelated replies",
  { timeout: 3000 },
  async () => {
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      const request = decodeEnvelope(peer.frames[7]);
      await peer.data("default", "other", Uint8Array.of(1));
      await peer.data("default", "other", Uint8Array.of(2));
      await peer.data("default", "peer", envelope("reply", request.id));
      await peer.ok();
      return true;
    });
    const node = await Node.connect("node", relay.endpoint, {
      inboxSize: 1,
      timeout: 0.04,
    });
    try {
      await assert.rejects(node.request("peer", new Uint8Array()), ReceiptTimeout);
      assert.equal(node.receiveNowait().payload[0], 1);
      assert.equal((await node.receive(bounded())).payload[0], 2);
      assert.equal(
        decodeEnvelope((await node.receive(bounded())).payload).kind,
        "reply",
      );
    } finally {
      await node.close();
      await relay.close();
    }
  },
);
