import assert from "node:assert/strict";
import test from "node:test";
import {
  decodeEnvelope,
  encodeEnvelope,
  Node,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";
import { fakeRelay } from "../../../../helpers/nodalwire/client/node/fake-relay.mjs";

test("reader-observed first terminal event wins both reply/error wire orders", {
  timeout: 3000,
}, async () => {
  for (const replyFirst of [true, false]) {
    const relay = await fakeRelay(async (peer) => {
      if (peer.command !== "SEND") return;
      const { id } = decodeEnvelope(peer.frames[7]);
      const reply = encodeEnvelope({ kind: "reply", id, payload: Uint8Array.of(7) });
      if (replyFirst) await peer.data("default", "peer", reply);
      await peer.error("destination_unavailable");
      if (!replyFirst) await peer.data("default", "peer", reply);
      return true;
    });
    const node = await Node.connect("node", relay.endpoint);
    try {
      const result = node.request("peer", new Uint8Array());
      if (replyFirst) {
        assert.equal((await result).payload[0], 7);
        assert.equal(node.receiveNowait(), undefined);
      } else {
        await assert.rejects(
          result,
          (error) =>
            error instanceof RelayError && error.code === "destination_unavailable",
        );
        const late = await node.receive({ signal: AbortSignal.timeout(1000) });
        assert.equal(decodeEnvelope(late.payload).payload[0], 7);
      }
    } finally {
      await node.close();
      await relay.close();
    }
  }
});
