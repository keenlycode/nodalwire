import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import test from "node:test";
import { setTimeout as sleep } from "node:timers/promises";
import {
  Node,
  ReceiptTimeout,
  RelayError,
} from "../../../../../src/nodalwire/client/node/dist/index.js";
import {
  fakeRelay,
  TOKEN,
} from "../../../../helpers/nodalwire/client/node/fake-relay.mjs";

const status = (code) => (error) => error instanceof RelayError && error.code === code;
const bounded = () => ({ signal: AbortSignal.timeout(1000) });

test(
  "AR2 protected-default admission, network selectors, membership receipts and snapshots",
  { timeout: 3000 },
  async () => {
    let change = "1";
    const relay = await fakeRelay(async (peer) => {
      if (peer.command === "JOIN" || peer.command === "LEAVE") {
        await peer.ok(peer.frames[5], change);
        return true;
      }
    }, { memberships: "[]" });
    const node = await Node.connect("node", relay.endpoint);
    try {
      const joined = await node.join("team", "fixture-token");
      assert.deepEqual(joined, { network: "team", joined: true, changed: true });
      assert.ok(Object.isFrozen(joined));
      change = "0";
      assert.deepEqual(await node.join("team", "fixture-token"), {
        network: "team",
        joined: true,
        changed: false,
      });
      assert.deepEqual(await node.leave("team"), {
        network: "team",
        joined: false,
        changed: false,
      });
      await node.join("other");
      const bytes = Uint8Array.of(100, 1, 2, 200);
      const sent = node.send("peer", bytes.subarray(1, 3), { network: "team" });
      bytes.fill(0);
      await sent;
      await node.send("peer", new Uint8Array());
      const sends = relay.seen.filter((frames) => frames[2].toString() === "SEND");
      assert.equal(sends[0][5].toString(), "team");
      assert.equal(sends[0][6].toString(), "peer");
      assert.deepEqual([...sends[0][7]], [1, 2]);
      assert.equal(sends[1][5].toString(), "default");
      assert.ok(relay.seen.every((frames) => frames[1].toString() === "AR2"));
      const joins = relay.seen.filter((frames) => frames[2].toString() === "JOIN");
      assert.equal(joins[0][6].toString(), "fixture-token");
      assert.equal(joins.at(-1)[6].length, 0);
      const peer = relay.peers.get("node");
      await peer.data("team", "peer", Uint8Array.of(255, 0));
      assert.deepEqual(await node.receive(bounded()), {
        network: "team",
        sender: "peer",
        payload: Uint8Array.of(255, 0),
      });
      for (const credential of ["", " ", "\n", "é", "x".repeat(1025), "\ud800"]) {
        await assert.rejects(node.join("team", credential), {
          name: "TypeError",
          message: "invalid join credential",
        });
      }
      for (const network of ["", "bad space", "x".repeat(129), "é"]) {
        await assert.rejects(node.join(network), TypeError);
        await assert.rejects(node.leave(network), TypeError);
        await assert.rejects(
          node.send("peer", new Uint8Array(), { network }),
          TypeError,
        );
      }
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test(
  "typed success validates exact shape, network and changed; errors never echo wire values",
  { timeout: 3000 },
  async () => {
    let response = (peer) => peer.ok("extra");
    const relay = await fakeRelay(async (peer) => {
      if (
        peer.command === "SEND" || peer.command === "JOIN" || peer.command === "LEAVE"
      ) {
        await response(peer);
        return true;
      }
    });
    const node = await Node.connect("node", relay.endpoint);
    try {
      await assert.rejects(
        node.send("peer", new Uint8Array()),
        status("invalid_receipt"),
      );
      for (
        const extra of [["wrong", "1"], ["team", "yes"], ["team"], [
          "team",
          "1",
          "extra",
        ], [Buffer.from([0xf4, 0x65, 0x61, 0x6d]), "1"]]
      ) {
        response = (peer) => peer.ok(...extra);
        await assert.rejects(node.join("team"), status("invalid_receipt"));
        await assert.rejects(node.leave("team"), status("invalid_receipt"));
      }
      for (
        const code of [
          "join_denied",
          "not_member",
          "destination_not_member",
          "network_not_found",
        ]
      ) {
        response = (peer) => peer.error(code);
        await assert.rejects(node.send("peer", new Uint8Array()), status(code));
      }
      response = (peer) => peer.error("secret-fixture-invalid-code");
      await assert.rejects(node.join("team"), { message: "invalid_receipt" });
      response = (peer) =>
        peer.raw("AR2", "ERROR", TOKEN, peer.rid, "join_denied", "extra");
      await assert.rejects(node.join("team"), status("invalid_receipt"));
    } finally {
      await node.close();
      await relay.close();
    }
  },
);

test("HELLO rejects malformed metadata and never installs a partial incarnation", {
  timeout: 5000,
}, async () => {
  for (
    const extra of [
      ["bad", "10", "1024", "[]"],
      [TOKEN, "Infinity", "1024", "[]"],
      [TOKEN, "0.01", "1024", "[]"],
      [TOKEN, "3601", "1024", "[]"],
      [TOKEN, "10", "0", "[]"],
      [TOKEN, "10", "2147483647", "[]"],
      [TOKEN, "10", "1.5", "[]"],
      [TOKEN, "10", "1024", '["other"]'],
      [TOKEN, "10", "1024", "[]", "extra"],
      [TOKEN, "10", "1024"],
    ]
  ) {
    const relay = await fakeRelay(async (peer) => {
      if (peer.command === "HELLO") {
        await peer.ok(...extra);
        return true;
      }
    });
    try {
      await assert.rejects(
        Node.connect("node", relay.endpoint),
        status("invalid_receipt"),
      );
      assert.deepEqual(relay.seen.map((frames) => frames[2].toString()), ["HELLO"]);
    } finally {
      await relay.close();
    }
  }
});

test("AR1 never admits or triggers downgrade; stale DATA/receipt frames never match", {
  timeout: 3000,
}, async () => {
  const old = await fakeRelay(async (peer) => {
    if (peer.command === "HELLO") {
      await peer.raw("AR1", "OK", "", peer.rid, TOKEN, "10", "1048576");
      return true;
    }
  });
  try {
    await assert.rejects(
      Node.connect("node", old.endpoint, { timeout: 0.04 }),
      ReceiptTimeout,
    );
    assert.equal(old.seen.length, 1);
    assert.equal(old.seen[0][1].toString(), "AR2");
  } finally {
    await old.close();
  }
  const relay = await fakeRelay(async (peer) => {
    if (peer.command === "SEND") {
      await peer.raw("AR2", "OK", "stale-token", peer.rid);
      await peer.raw("AR2", "OK", TOKEN, "unknown-id");
      await peer.data("team", "peer", Uint8Array.of(1), "stale-token");
      await peer.data(Buffer.from([0xf4, 0x65, 0x61, 0x6d]), "peer", Uint8Array.of(2));
      await peer.data("team", Buffer.from([0xf0, 0x65, 0x65, 0x72]), Uint8Array.of(3));
      await peer.data("team", "peer", Uint8Array.of(4));
      return true;
    }
  });
  const node = await Node.connect("node", relay.endpoint, { timeout: 0.05 });
  try {
    const sent = assert.rejects(node.send("peer", new Uint8Array()), ReceiptTimeout);
    assert.deepEqual(await node.receive(bounded()), {
      network: "team",
      sender: "peer",
      payload: Uint8Array.of(4),
    });
    await sent;
    assert.equal(node.receiveNowait(), undefined);
  } finally {
    await node.close();
    await relay.close();
  }
});

test(
  "full inbox pauses receipts, receiveNowait releases space, queued DATA survives leave/close",
  { timeout: 3000 },
  async () => {
    const relay = await fakeRelay();
    const node = await Node.connect("node", relay.endpoint, {
      inboxSize: 1,
      timeout: 0.1,
    });
    try {
      const peer = relay.peers.get("node");
      await peer.data("team", "peer", Uint8Array.of(1));
      await peer.data("team", "peer", Uint8Array.of(2));
      await sleep(15);
      await assert.rejects(
        node.join("team", undefined, { timeout: 0.03 }),
        ReceiptTimeout,
      );
      assert.equal(node.receiveNowait().payload[0], 1);
      assert.equal((await node.receive(bounded())).payload[0], 2);
      await node.leave("team");
      await peer.data("team", "peer", Uint8Array.of(3));
      await sleep(10);
      await node.close();
      assert.equal(node.receiveNowait().payload[0], 3);
      assert.equal(node.receiveNowait(), undefined);
      await assert.rejects(node.receive(), status("closed"));
      await assert.rejects(node.join("team"), status("closed"));
      await assert.rejects(node.leave("team"), status("closed"));
    } finally {
      await node.close();
      await relay.close();
    }
  },
);
