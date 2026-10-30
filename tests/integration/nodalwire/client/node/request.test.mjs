import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { Buffer } from "node:buffer";
import {
  Node,
  ReceiptTimeout,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";
import {
  fakeRelay,
  TOKEN,
} from "../../../../helpers/nodalwire/client/node/fake-relay.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("../../../../fixtures/nwm3/wire.json", import.meta.url)),
);
const status = (code) => (error) => error instanceof RelayError && error.code === code;
const id = (frame) => frame.toString("ascii");
const decodeFrame = (frame) =>
  frame.ascii !== undefined
    ? Buffer.from(frame.ascii, "ascii")
    : Buffer.from(frame.hex, "hex");

function withLocalToken(frames) {
  const packet = frames.map(decodeFrame);
  packet[2] = Buffer.from(TOKEN);
  return packet;
}

test(
  "request matches reply_to, sender, and network while shared correlation fixtures remain inbox data",
  {
    timeout: 3000,
  },
  async () => {
    const unrelated = [];
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      const requestId = id(peer.frames[4]);
      assert.equal(peer.frames[7].length, 0);
      const cases = fixture.correlation.cases.filter(({ owner }) => owner === "inbox");
      for (const item of cases) {
        const packet = withLocalToken(item.data);
        await peer.raw(...packet);
        unrelated.push(item.name);
      }
      await peer.data(
        "c".repeat(32),
        "default",
        "gamma",
        requestId,
        Buffer.from("wrong sender"),
      );
      await peer.data(
        "d".repeat(32),
        "red",
        "beta",
        requestId,
        Buffer.from("wrong network"),
      );
      unrelated.push("wrong sender", "wrong network");
      await peer.data(
        "2".repeat(32),
        "default",
        "beta",
        requestId,
        Buffer.from("native reply"),
      );
      return true; // reply, not SEND OK, owns the operation
    });
    const node = await Node.connect("alpha", relay.endpoint);
    try {
      const reply = await node.request("beta", Uint8Array.of(0, 255), {
        timeout: 0.5,
      });
      assert.equal(reply.id, "2".repeat(32));
      assert.equal(reply.reply_to.length, 32);
      assert.equal(reply.sender, "beta");
      assert.equal(reply.network, "default");
      assert.equal(Buffer.from(reply.payload).toString(), "native reply");
      const queued = [];
      for (let i = 0; i < unrelated.length; i++) {
        queued.push(
          await node.receive({ signal: AbortSignal.timeout(1000) }),
        );
      }
      assert.deepEqual(
        queued.slice(0, 4).map(({ id: messageId }) => messageId),
        fixture.correlation.cases.filter(({ owner }) => owner === "inbox").map((item) =>
          Buffer.from(item.data[3].ascii).toString()
        ),
      );
      assert.equal(queued[4].sender, "gamma");
      assert.equal(queued[4].reply_to, reply.reply_to);
      assert.equal(queued[5].network, "red");
      assert.equal(queued[5].reply_to, reply.reply_to);
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "both first-terminal orderings are honored; late and duplicate DATA stay in inbox",
  {
    timeout: 3000,
  },
  async () => {
    for (const replyFirst of [true, false]) {
      const relay = await fakeRelay(async (peer) => {
        if (peer.command !== "SEND") return;
        const requestId = id(peer.frames[4]);
        const deliver = () =>
          peer.data(
            "3".repeat(32),
            "default",
            "beta",
            requestId,
            Buffer.from("reply"),
          );
        if (replyFirst) {
          await deliver();
          await deliver(); // Duplicate after reader ownership must enter the inbox.
        }
        await peer.error("destination_unavailable");
        if (!replyFirst) await deliver();
        return true;
      });
      const node = await Node.connect("alpha", relay.endpoint);
      try {
        const result = node.request("beta", Uint8Array.of(1), { timeout: 0.5 });
        if (replyFirst) {
          assert.equal(Buffer.from((await result).payload).toString(), "reply");
          const duplicate = await node.receive({ signal: AbortSignal.timeout(1000) });
          assert.equal(duplicate.id, "3".repeat(32));
          assert.equal(
            duplicate.reply_to,
            relay.seen.find((frames) => frames[2].toString() === "SEND")[4].toString(),
          );
        } else {
          await assert.rejects(result, status("destination_unavailable"));
          assert.equal(
            Buffer.from(
              (await node.receive({ signal: AbortSignal.timeout(1000) }))
                .payload,
            ).toString(),
            "reply",
          );
        }
      } finally {
        await node.close();
        await relay.close();
      }
    }
  },
);

test(
  "malformed/stale DATA fixture packets are discarded; valid NWR1-looking payload stays opaque",
  {
    timeout: 3000,
  },
  async () => {
    const relay = await fakeRelay(undefined, { maxPayload: 256 });
    const node = await Node.connect("alpha", relay.endpoint);
    try {
      const peer = relay.peers.get("alpha");
      for (const [index, item] of fixture.client_discard.entries()) {
        const packet = item.name === "stale_incarnation"
          ? item.data.map(decodeFrame)
          : withLocalToken(item.data);
        await peer.raw(...packet);
        const markerId = (index + 1).toString(16).padStart(32, "0");
        await peer.data(
          markerId,
          "default",
          "beta",
          "",
          Buffer.from(item.name),
        );
        const marker = await node.receive({
          signal: AbortSignal.timeout(1000),
        });
        assert.equal(marker.id, markerId, `${item.name} must be discarded`);
      }
      const opaque = fixture.routes.find(({ name }) => name === "nwr1_is_opaque");
      await peer.raw(...withLocalToken(opaque.data));
      const received = await node.receive({
        signal: AbortSignal.timeout(1000),
      });
      assert.equal(received.id, opaque.message.id);
      assert.deepEqual(
        received.payload,
        Uint8Array.from(Buffer.from(opaque.message.payload_hex, "hex")),
      );
      assert.equal(node.receiveNowait(), undefined);
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "SEND rejection and malformed receipt clean waiters; later DATA is ordinary and no retry occurs",
  {
    timeout: 3000,
  },
  async () => {
    let mode = "reject";
    let sends = 0;
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      sends++;
      const requestId = id(peer.frames[4]);
      if (mode === "reject") {
        await peer.error("route_denied");
        await peer.data(
          "4".repeat(32),
          "default",
          "beta",
          requestId,
          Buffer.from("late"),
        );
      } else if (mode === "malformed") {
        await peer.ok("extra");
        await peer.data(
          "5".repeat(32),
          "default",
          "beta",
          requestId,
          Buffer.from("after invalid receipt"),
        );
      }
      return true;
    });
    const node = await Node.connect("alpha", relay.endpoint, { timeout: 0.08 });
    try {
      await assert.rejects(
        node.request("beta", Uint8Array.of(1)),
        status("route_denied"),
      );
      assert.equal(
        Buffer.from(
          (await node.receive({ signal: AbortSignal.timeout(1000) })).payload,
        )
          .toString(),
        "late",
      );
      mode = "malformed";
      await assert.rejects(
        node.request("beta", Uint8Array.of(2)),
        status("invalid_receipt"),
      );
      assert.equal(
        Buffer.from(
          (await node.receive({ signal: AbortSignal.timeout(1000) })).payload,
        )
          .toString(),
        "after invalid receipt",
      );
      mode = "silent";
      await assert.rejects(
        node.request("beta", Uint8Array.of(3)),
        ReceiptTimeout,
      );
      assert.equal(sends, 3, "no retry or replay");
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "request deadline and abort clean up without closing shared reader; late replies remain readable",
  {
    timeout: 3000,
  },
  async () => {
    const sent = [];
    const relay = await fakeRelay((peer) => {
      if (peer.command !== "SEND") return;
      sent.push({ peer, requestId: id(peer.frames[4]) });
      return true;
    });
    const node = await Node.connect("alpha", relay.endpoint, { timeout: 0.05 });
    try {
      await assert.rejects(
        node.request("beta", new Uint8Array()),
        ReceiptTimeout,
      );
      const controller = new AbortController();
      const aborted = node.request("beta", new Uint8Array(), {
        signal: controller.signal,
        timeout: 1,
      });
      await sleep(5);
      controller.abort(new Error("test abort"));
      await assert.rejects(aborted, /test abort/);
      const peer = sent[1].peer;
      await peer.data(
        "6".repeat(32),
        "default",
        "beta",
        sent[0].requestId,
        Buffer.from("timeout late"),
      );
      await peer.data(
        "7".repeat(32),
        "default",
        "beta",
        sent[1].requestId,
        Buffer.from("abort late"),
      );
      const messages = [
        await node.receive({ signal: AbortSignal.timeout(1000) }),
        await node.receive({ signal: AbortSignal.timeout(1000) }),
      ];
      assert.deepEqual(
        messages.map((message) => Buffer.from(message.payload).toString()),
        ["timeout late", "abort late"],
      );
      assert.equal(sent.length, 2, "one SEND per request; no retries");
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "full ordinary inbox backpressure can time out request without dropping native messages",
  {
    timeout: 3000,
  },
  async () => {
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      const requestId = id(peer.frames[4]);
      await peer.data(
        "8".repeat(32),
        "default",
        "other",
        "",
        Buffer.from("one"),
      );
      await peer.data(
        "9".repeat(32),
        "default",
        "other",
        "",
        Buffer.from("two"),
      );
      await peer.data(
        "a".repeat(32),
        "default",
        "beta",
        requestId,
        Buffer.from("reply"),
      );
      await peer.ok();
      return true;
    });
    const node = await Node.connect("alpha", relay.endpoint, {
      inboxSize: 1,
      timeout: 0.04,
    });
    try {
      await assert.rejects(
        node.request("beta", new Uint8Array()),
        ReceiptTimeout,
      );
      assert.equal(Buffer.from(node.receiveNowait().payload).toString(), "one");
      assert.equal(
        Buffer.from(
          (await node.receive({ signal: AbortSignal.timeout(1000) })).payload,
        )
          .toString(),
        "two",
      );
      assert.equal(
        Buffer.from(
          (await node.receive({ signal: AbortSignal.timeout(1000) })).payload,
        )
          .toString(),
        "reply",
      );
    } finally {
      await node.close();
      await relay.close();
    }
  },
);
