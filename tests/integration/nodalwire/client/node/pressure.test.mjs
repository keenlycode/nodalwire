import assert from "node:assert/strict";
import test from "node:test";
import { Router } from "../../../../helpers/nodalwire/client/node/deps.mjs";
import {
  Node,
  ReceiptTimeout,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";

// Bounded functional HWM check, not a load/stress benchmark (<= 16 MiB attempted).
test("non-reading connected peer fills the native HWM without a JS outbound queue", {
  timeout: 3000,
}, async () => {
  const router = new Router({ linger: 0, receiveHighWaterMark: 1 });
  await router.bind("tcp://127.0.0.1:*");
  const admission = (async () => {
    const frames = await router.receive();
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
    // Deliberately no more reads; this actually connected native peer never drains.
  })();
  let node;
  try {
    node = await Node.connect("pressure", router.lastEndpoint, {
      sendHwm: 1,
      receiveHwm: 1,
    });
    await admission;
    let full = false;
    let acceptedWithoutReceipt = false;
    const payload = new Uint8Array(256 * 1024);
    for (let i = 0; i < 64; i++) {
      try {
        await node.send("destination", payload, { timeout: 0.01 });
        assert.fail("silent peer cannot provide routing receipts");
      } catch (error) {
        if (error instanceof RelayError && error.code === "local_queue_full") {
          full = true;
          break;
        }
        assert.ok(error instanceof ReceiptTimeout, String(error));
        acceptedWithoutReceipt = true;
      }
    }
    assert.ok(
      acceptedWithoutReceipt,
      "at least one native send accepted without an AR2 receipt",
    );
    assert.ok(full, "bounded probe reached native EAGAIN");
  } finally {
    if (node) {
      try {
        await node.close({ timeout: 0.02 });
      } catch (error) {
        assert.ok(
          error instanceof ReceiptTimeout ||
            (error instanceof RelayError && error.code === "local_queue_full"),
        );
      }
    }
    router.close();
    await admission;
  }
});
