import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { Router } from "../../../../helpers/nodalwire/client/node/deps.mjs";
import {
  Node,
  ReceiptTimeout,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";
const status = (code) => (error) => error instanceof RelayError && error.code === code;

async function silentRelay(admit = true) {
  const router = new Router({
    linger: 0,
    receiveHighWaterMark: 1,
    sendHighWaterMark: 1,
  });
  await router.bind("tcp://127.0.0.1:*");
  const seen = [];
  const reader = (async () => {
    try {
      for await (const frames of router) {
        seen.push(frames[2].toString());
        if (admit && frames[2].toString() === "HELLO") {
          await router.send([
            frames[0],
            "NWM3",
            "OK",
            "",
            frames[3],
            "0123456789abcdef0123456789abcdef",
            "10",
            "1048576",
            '["default"]',
          ]);
        }
      }
    } catch (error) {
      if (!router.closed) throw error;
    }
  })();
  return {
    endpoint: router.lastEndpoint,
    seen,
    async close() {
      router.close();
      await reader;
    },
  };
}

test(
  "silent admission times out or aborts and joins native receive",
  { timeout: 3000 },
  async () => {
    const relay = await silentRelay(false);
    try {
      await assert.rejects(
        Node.connect("timeout", relay.endpoint, { timeout: 0.06 }),
        ReceiptTimeout,
      );
      const controller = new AbortController();
      const attempt = Node.connect("abort", relay.endpoint, {
        signal: controller.signal,
      });
      await sleep(20);
      controller.abort();
      await assert.rejects(attempt, { name: "AbortError" });
      assert.ok(relay.seen.includes("HELLO"));
    } finally {
      await relay.close();
    }
  },
);

test(
  "no receipts: timeout/cancellation remove correlation; concurrent native writer has no backlog",
  { timeout: 3000 },
  async () => {
    const relay = await silentRelay();
    const node = await Node.connect("client", relay.endpoint, {
      timeout: 0.08,
      maxPending: 1,
    });
    try {
      const first = node.send("destination", Uint8Array.of(1));
      await assert.rejects(
        node.send("destination", Uint8Array.of(2)),
        status("pending_full"),
      );
      await assert.rejects(first, ReceiptTimeout);
      const controller = new AbortController();
      const cancelled = node.send("destination", Uint8Array.of(3), {
        signal: controller.signal,
      });
      await sleep(10);
      controller.abort();
      await assert.rejects(cancelled, { name: "AbortError" });
      await assert.rejects(
        node.send("destination", Uint8Array.of(4)),
        ReceiptTimeout,
      );
      const receiver = assert.rejects(node.receive(), status("closed"));
      const close = node.close({ timeout: 0.04 });
      const joined = node.close();
      await assert.rejects(close, ReceiptTimeout);
      await joined;
      await receiver;
      await node.close();
    } finally {
      await node.close();
      await relay.close();
    }

    const relay2 = await silentRelay();
    const node2 = await Node.connect("writer", relay2.endpoint, {
      timeout: 0.04,
    });
    try {
      const first = node2.send("destination", Uint8Array.of(1));
      await assert.rejects(
        node2.send("destination", Uint8Array.of(2)),
        status("local_queue_full"),
      );
      await assert.rejects(first, ReceiptTimeout);
    } finally {
      await assert.rejects(node2.close(), ReceiptTimeout);
      await relay2.close();
    }
  },
);
