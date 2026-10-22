import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { Router } from "zeromq";
import { Node, ReceiptTimeout, RelayError } from "../dist/index.js";
import { Inbox } from "../dist/inbox.js";
import { localEndpoint, validName } from "../dist/protocol.js";

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
            "AR2",
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

test("logical names and local endpoints validate before transport", async () => {
  assert.equal(localEndpoint("tcp://localhost:5555"), "tcp://127.0.0.1:5555");
  assert.equal(localEndpoint("tcp://127.12.3.4:1234"), "tcp://127.12.3.4:1234");
  assert.equal(localEndpoint("tcp://[::1]:1234"), "tcp://[::1]:1234");
  for (
    const endpoint of [
      "ipc:///tmp/x",
      "tcp://0.0.0.0:5",
      "tcp://example.org:5",
      "tcp://127.0.0.1:*",
      "tcp://127.0.0.1:65536",
      "tcp://[::ffff:127.0.0.1]:5",
    ]
  ) {
    await assert.rejects(Node.connect("valid", endpoint), TypeError);
  }
  for (const name of ["", " leading", "x\n", "x".repeat(129)]) {
    assert.equal(validName(name), false);
    await assert.rejects(Node.connect(name), TypeError);
  }
  await assert.rejects(Node.connect("valid", undefined, { inboxSize: 0 }), RangeError);
  await assert.rejects(Node.connect("valid", undefined, { timeout: 0 }), RangeError);
});

test("bounded inbox preserves order, wakes canceled and closed waiters", async () => {
  const inbox = new Inbox(1);
  const first = { network: "default", sender: "a", payload: Uint8Array.of(1) };
  const second = { network: "default", sender: "a", payload: Uint8Array.of(2) };
  await inbox.put(first);
  let accepted = false;
  const held = inbox.put(second).then(() => accepted = true);
  await sleep(10);
  assert.equal(accepted, false);
  assert.equal(await inbox.get(), first);
  await held;
  inbox.close();
  assert.equal(await inbox.get(), second);
  await assert.rejects(inbox.get(), status("closed"));
  const empty = new Inbox(1);
  const controller = new AbortController();
  const cancelled = empty.get(controller.signal);
  controller.abort();
  await assert.rejects(cancelled, { name: "AbortError" });
  const waiting = empty.get();
  empty.close();
  await assert.rejects(waiting, status("closed"));
});

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
      await assert.rejects(node.send("destination", Uint8Array.of(4)), ReceiptTimeout);
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
    const node2 = await Node.connect("writer", relay2.endpoint, { timeout: 0.04 });
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
