import assert from "node:assert/strict";
import test from "node:test";
import { Node } from "../../../../../../src/nodalwire/client/node/dist/index.js";
import {
  localEndpoint,
  validName,
} from "../../../../../../src/nodalwire/client/node/dist/protocol.js";

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
