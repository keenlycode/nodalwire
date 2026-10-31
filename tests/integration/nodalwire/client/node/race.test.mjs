import assert from "node:assert/strict";
import test from "node:test";
import { Buffer } from "node:buffer";
import {
  Node,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";
import { fakeRelay } from "../../../../helpers/nodalwire/client/node/fake-relay.mjs";

const status = (code) => (error) => error instanceof RelayError && error.code === code;

test(
  "reader-observed first terminal event wins for both NWM3 reply/receipt wire orders",
  {
    timeout: 3000,
  },
  async () => {
    for (const replyFirst of [true, false]) {
      const relay = await fakeRelay(async (peer) => {
        if (peer.command !== "SEND") return;
        const requestId = peer.frames[4].toString("ascii");
        const deliver = () =>
          peer.data(
            "a".repeat(32),
            "default",
            "peer",
            requestId,
            Buffer.from("answer"),
          );
        if (replyFirst) await deliver();
        await peer.error("destination_unavailable");
        if (!replyFirst) await deliver();
        return true;
      });
      const node = await Node.connect("node", relay.endpoint);
      try {
        const result = node.request("peer", new Uint8Array());
        if (replyFirst) {
          const message = await result;
          assert.equal(Buffer.from(message.payload).toString(), "answer");
          assert.equal(node.receiveNowait(), undefined);
        } else {
          await assert.rejects(result, status("destination_unavailable"));
          const late = await node.receive({ signal: AbortSignal.timeout(1000) });
          assert.equal(Buffer.from(late.payload).toString(), "answer");
        }
      } finally {
        await node.close();
        await relay.close();
      }
    }
  },
);
