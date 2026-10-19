import assert from "node:assert/strict";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import { Router } from "zeromq";
import { Node, ReceiptTimeout } from "../dist/index.js";

// Own an ephemeral port, then release it: no relay exists for these attempts.
test("connect deadline/abort interrupt and join a native pending HELLO send", {
  timeout: 2000,
}, async () => {
  const router = new Router({ linger: 0 });
  await router.bind("tcp://127.0.0.1:*");
  const endpoint = router.lastEndpoint;
  router.close();
  await assert.rejects(
    Node.connect("timeout", endpoint, { timeout: 0.05 }),
    ReceiptTimeout,
  );
  const controller = new AbortController();
  const attempt = Node.connect("abort", endpoint, { signal: controller.signal });
  await sleep(20);
  controller.abort();
  await assert.rejects(attempt, { name: "AbortError" });
});
