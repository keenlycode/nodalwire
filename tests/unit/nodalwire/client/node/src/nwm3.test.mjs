import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import { readFileSync } from "node:fs";
import test from "node:test";
import { Node } from "../../../../../../src/nodalwire/client/node/dist/index.js";
import {
  fakeRelay,
  TOKEN,
} from "../../../../../helpers/nodalwire/client/node/fake-relay.mjs";

const fixture = JSON.parse(
  readFileSync(new URL("../../../../../fixtures/nwm3/wire.json", import.meta.url)),
);
const decodeFrame = (frame) =>
  frame.ascii !== undefined
    ? Buffer.from(frame.ascii, "ascii")
    : Buffer.from(frame.hex, "hex");

test("NWM3 send uses receipt correlation ID and returns it after acceptance", async () => {
  const route = fixture.routes.find(({ name }) => name === "binary");
  const relay = await fakeRelay(async (peer) => {
    if (peer.command === "SEND") {
      assert.equal(peer.frames[1].toString(), "NWM3");
      assert.equal(peer.frames[2].toString(), "SEND");
      assert.equal(peer.frames.length, 9); // ROUTER address plus eight NWM3 frames.
      assert.match(peer.frames[4].toString(), /^[0-9a-f]{32}$/);
      assert.deepEqual(
        peer.frames.slice(5).map((frame) => Buffer.from(frame)),
        route.send.slice(4).map(decodeFrame),
      );
      await peer.ok();
    } else if (peer.command === "HELLO") {
      await peer.ok("0123456789abcdef0123456789abcdef", "10.0", "256", '["default"]');
    } else if (peer.command === "CLOSE") {
      await peer.ok();
    }
    return true;
  });
  const node = await Node.connect("alpha", relay.endpoint);
  try {
    const payload = Uint8Array.of(0, 255);
    const sending = node.send("beta", payload);
    payload[0] = 99;
    const id = await sending;
    assert.match(id, /^[0-9a-f]{32}$/);
    assert.equal(relay.seen.some((frames) => frames[2].toString() === "SEND"), true);
  } finally {
    await node.close();
    await relay.close();
  }
});

test("NWM3 fixture framing retains raw payload and metadata in the ordinary inbox", async () => {
  const route = fixture.routes.find(({ name }) => name === "reply_new_id");
  const data = route.data.map(decodeFrame);
  data[2] = Buffer.from(TOKEN);
  const relay = await fakeRelay(async (peer) => {
    if (peer.command === "HELLO") {
      await peer.ok("0123456789abcdef0123456789abcdef", "10.0", "256", '["default"]');
    } else if (peer.command === "CLOSE") await peer.ok();
    else return true;
    return true;
  });
  const node = await Node.connect("beta", relay.endpoint);
  try {
    await relay.peers.get("beta").raw(...data);
    const message = await node.receive({ signal: AbortSignal.timeout(1000) });
    assert.deepEqual(message, {
      id: route.message.id,
      sender: route.message.sender,
      network: route.message.network,
      reply_to: route.message.reply_to,
      payload: Uint8Array.from(Buffer.from(route.message.payload_hex, "hex")),
    });
  } finally {
    await node.close();
    await relay.close();
  }
});
