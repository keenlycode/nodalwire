import assert from "node:assert/strict";
import { Buffer } from "node:buffer";
import process from "node:process";
import { setTimeout as sleep } from "node:timers/promises";
const { decodeEnvelope, Node, ReceiptTimeout, RelayError } = await import(
  process.env.NODALWIRE_CLIENT_MODULE ??
    new URL(
      "../../../../../src/nodalwire/client/node/dist/index.js",
      import.meta.url,
    ).href
);

const endpoint = process.argv[2];
const mode = process.argv[3] ?? "open";
const status = (code) => (error) => error instanceof RelayError && error.code === code;
const boundedReceive = (node) => node.receive({ signal: AbortSignal.timeout(1500) });

if (mode === "protected") {
  const node = await Node.connect("js-node", endpoint);
  try {
    await assert.rejects(
      node.send("py-echo", new Uint8Array()),
      status("not_member"),
    );
    await assert.rejects(node.join("default"), status("join_denied"));
    await assert.rejects(
      node.join("default", "wrong-fixture-token"),
      status("join_denied"),
    );
    assert.deepEqual(await node.join("default", "fixture-default-token"), {
      network: "default",
      joined: true,
      changed: true,
    });
    assert.equal(
      (await node.join("default", "fixture-default-token")).changed,
      false,
    );
    await node.send("py-echo", Uint8Array.of(255));
    assert.deepEqual(await boundedReceive(node), {
      network: "default",
      sender: "py-echo",
      payload: Uint8Array.of(255),
    });
    await node.leave("default");
    assert.equal((await node.leave("default")).changed, false);
    await assert.rejects(
      node.send("py-echo", new Uint8Array()),
      status("not_member"),
    );
  } finally {
    await node.close();
  }
  console.log(
    "PASS protected default: zero-membership admission, explicit join/leave and errors",
  );
} else {
  await openScenario();
}

async function openScenario() {
  const alice = await Node.connect("js-node", endpoint);
  try {
    for (
      const payload of [
        Uint8Array.from({ length: 256 }, (_, i) => i),
        Buffer.alloc(0),
        Uint8Array.of(99, 0, 255, 88).subarray(1, 3),
      ]
    ) {
      const snapshot = Uint8Array.from(payload);
      const sent = alice.send("py-echo", payload);
      payload.fill(42);
      await sent;
      const message = await boundedReceive(alice);
      assert.equal(message.network, "default");
      assert.equal(message.sender, "py-echo");
      assert.deepEqual(message.payload, snapshot);
    }
    await assert.rejects(
      alice.send("missing", new Uint8Array()),
      status("destination_unavailable"),
    );
    await assert.rejects(
      alice.send("py-denied", new Uint8Array()),
      status("route_denied"),
    );
    await assert.rejects(
      alice.send("py-echo", new Uint8Array(1025)),
      status("payload_too_large"),
    );
    await assert.rejects(
      Node.connect("js-node", endpoint),
      status("duplicate_name"),
    );
    await sleep(1050); // >3 lease periods: bounded application-idle heartbeat check.
    await assert.rejects(
      Node.connect("js-node", endpoint),
      status("duplicate_name"),
    );
    await alice.send("py-echo", Uint8Array.of(1));
    assert.deepEqual((await boundedReceive(alice)).payload, Uint8Array.of(1));
    const canceled = new AbortController();
    const waiting = alice.receive({ signal: canceled.signal });
    canceled.abort();
    await assert.rejects(waiting, { name: "AbortError" });
    await alice.send("py-echo", Uint8Array.of(2));
    assert.deepEqual((await boundedReceive(alice)).payload, Uint8Array.of(2));

    await assert.rejects(
      alice.send("py-echo", new Uint8Array(), { network: "other" }),
      status("not_member"),
    );
    await alice.join("other");
    await alice.send("py-echo", Uint8Array.of(3), { network: "other" });
    assert.equal((await boundedReceive(alice)).network, "other");
    await assert.rejects(
      alice.join("missing-network"),
      status("network_not_found"),
    );
    await assert.rejects(alice.join("team"), status("join_denied"));
    await alice.join("team", "fixture-team-token");
    // Joining team does not leave other/default; omitting selector remains default.
    await alice.send("py-echo", Uint8Array.of(4));
    assert.equal((await boundedReceive(alice)).network, "default");
    await alice.leave("default");
    await assert.rejects(
      alice.send("py-echo", new Uint8Array()),
      status("not_member"),
    );
    await alice.send("py-echo", Uint8Array.of(5), { network: "team" });
    assert.equal((await boundedReceive(alice)).network, "team");
    for (
      const payload of [
        new Uint8Array(),
        Uint8Array.from({ length: 256 }, (_, i) => i),
      ]
    ) {
      const response = await alice.request("py-echo", payload, {
        network: "team",
      });
      assert.deepEqual(response, {
        network: "team",
        sender: "py-echo",
        payload,
      });
      assert.equal(
        Buffer.from((await boundedReceive(alice)).payload).toString(),
        "unrelated",
      );
    }
    await alice.send("py-echo", Buffer.from("python-request"), {
      network: "team",
    });
    const incoming = await boundedReceive(alice);
    const envelope = decodeEnvelope(incoming.payload);
    assert.equal(envelope.kind, "request");
    assert.equal(incoming.network, "team");
    await alice.reply(incoming, envelope.payload);
    assert.equal(
      Buffer.from((await boundedReceive(alice)).payload).toString(),
      "python-request-ok",
    );
    await alice.join("default");
    await alice.send("py-echo", Buffer.from("rotate-team-fixture"), {
      network: "team",
    });
    assert.equal(
      Buffer.from((await boundedReceive(alice)).payload).toString(),
      "rotated-team",
    );
    // Rotation changes future joins, not existing Python/Node memberships.
    await alice.send("py-echo", Uint8Array.of(6), { network: "team" });
    assert.equal((await boundedReceive(alice)).payload[0], 6);
    const newcomer = await Node.connect("newcomer", endpoint);
    try {
      await assert.rejects(
        newcomer.join("team", "fixture-team-token"),
        status("join_denied"),
      );
      assert.equal(
        (await newcomer.join("team", "fixture-team-new")).joined,
        true,
      );
    } finally {
      await newcomer.close();
    }
    await alice.send("py-echo", Buffer.from("remove-team-fixture"), {
      network: "team",
    });
    const acceptedBeforeRemoval = await boundedReceive(alice);
    assert.equal(acceptedBeforeRemoval.network, "team");
    assert.equal(
      Buffer.from(acceptedBeforeRemoval.payload).toString(),
      "accepted-before-remove",
    );
    const removed = await boundedReceive(alice);
    assert.equal(removed.network, "default");
    assert.equal(Buffer.from(removed.payload).toString(), "removed-team");
    await assert.rejects(
      alice.send("py-echo", new Uint8Array(), { network: "team" }),
      status("not_member"),
    );
    await assert.rejects(
      alice.join("team", "fixture-team-token"),
      status("join_denied"),
    );
    await alice.join("team", "fixture-team-new");
  } finally {
    await alice.close();
  }
  await assert.rejects(alice.receive(), status("closed"));
  assert.equal(alice.receiveNowait(), undefined);
  const replacement = await Node.connect("js-node", endpoint);
  await Promise.all([replacement.close(), replacement.close()]);
  await replacement.close();
  console.log(
    "PASS AR2 multi-membership/no fallback, binary request/reply both directions, unrelated DATA, rotation future joins/removal cutoff, heartbeat and release",
  );

  const source = await Node.connect("source", endpoint);
  const busy = await Node.connect("busy", endpoint, {
    inboxSize: 1,
    maxPending: 1,
    timeout: 0.15,
  });
  try {
    await source.send("busy", Uint8Array.of(10));
    await source.send("busy", Uint8Array.of(11));
    await sleep(30);
    const uncertain = busy.send("source", Uint8Array.of(12));
    await assert.rejects(
      busy.send("source", Uint8Array.of(13)),
      status("pending_full"),
    );
    assert.deepEqual((await boundedReceive(source)).payload, Uint8Array.of(12));
    await assert.rejects(uncertain, ReceiptTimeout);
    assert.deepEqual((await boundedReceive(busy)).payload, Uint8Array.of(10));
    assert.deepEqual((await boundedReceive(busy)).payload, Uint8Array.of(11));
    await busy.send("source", Uint8Array.of(14));
    assert.deepEqual((await boundedReceive(source)).payload, Uint8Array.of(14));
    await source.send("busy", Uint8Array.of(15));
    await sleep(30);
    await busy.close();
    assert.deepEqual((await busy.receive()).payload, Uint8Array.of(15));
    await assert.rejects(busy.receive(), status("closed"));
  } finally {
    await Promise.all([busy.close(), source.close()]);
  }
  console.log(
    "PASS bounded inbox/pending, honest after-effect timeout, queued receive after close",
  );

  const closerSource = await Node.connect("closer-source", endpoint);
  const closer = await Node.connect("closer", endpoint, { inboxSize: 1 });
  try {
    await closerSource.send("closer", Uint8Array.of(20));
    await closerSource.send("closer", Uint8Array.of(21));
    await sleep(30);
    const close = closer.close({ signal: AbortSignal.timeout(40) });
    const joined = closer.close();
    await assert.rejects(close, { name: "TimeoutError" });
    await joined;
    await closer.close();
    await assert.rejects(
      closer.send("closer-source", new Uint8Array()),
      status("closed"),
    );
  } finally {
    await Promise.all([closer.close(), closerSource.close()]);
  }
  console.log("PASS canceled blocked close with shared completing cleanup");
}
