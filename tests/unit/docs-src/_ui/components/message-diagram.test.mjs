import { test } from "node:test";
import assert from "node:assert/strict";
import path from "node:path";
import { requireDocs, source, toolRoot, root } from "../../../../helpers/docs.mjs";
const { build } = requireDocs("esbuild");
const compiled = await build({
  entryPoints: [path.join(source, "_ui/components/message-diagram/model.ts")],
  absWorkingDir: root, bundle: true, write: false, platform: "node", format: "esm",
  nodePaths: [path.join(toolRoot, "node_modules")],
});
const { getDiagramModel, isDiagramKind } = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);
const kinds = ["architecture", "send", "request-reply"];

function inside(inner, outer) {
  return inner.x >= outer.x && inner.y >= outer.y && inner.x + inner.width <= outer.x + outer.width && inner.y + inner.height <= outer.y + outer.height;
}
function overlaps(a, b) {
  return a.x < b.x + b.width && a.x + a.width > b.x && a.y < b.y + b.height && a.y + a.height > b.y;
}

test("Supported diagram kinds are explicit; unknown kinds and invalid dimensions reject", () => {
  for (const kind of kinds) assert.equal(isDiagramKind(kind), true);
  for (const kind of [null, undefined, "", "toString", "SEND", "unknown"]) {
    assert.equal(isDiagramKind(kind), false);
    assert.throws(() => getDiagramModel(kind, "wide"), RangeError);
  }
  assert.throws(() => getDiagramModel("send", "unknown"), RangeError);
  for (const width of [0, -1, Infinity, NaN]) assert.throws(() => getDiagramModel("send", "compact", width), RangeError);
});

test("All scenes keep native destination queues inside relay, never inside apps", () => {
  for (const kind of kinds) for (const layout of ["wide", "compact"]) {
    const model = getDiagramModel(kind, layout);
    const relay = model.nodes.find(n => n.role === "relay");
    const queues = model.nodes.filter(n => n.role === "native-queue");
    assert.equal(model.acceptanceBoundary, "relay-native-destination-queue");
    assert.equal(queues.length, kind === "request-reply" ? 2 : 1);
    for (const queue of queues) {
      assert.equal(queue.parent, relay.id);
      assert.ok(inside(queue, relay));
      for (const app of model.nodes.filter(n => n.role === "application")) assert.equal(inside(queue, app), false);
    }
    const byId = new Map(model.nodes.map(n => [n.id, n]));
    for (const edge of model.edges) {
      assert.ok(byId.has(edge.source)); assert.ok(byId.has(edge.target));
      assert.notEqual(edge.source, edge.target);
      assert.ok(edge.label.trim());
    }
    const acceptance = model.edges.find(e => e.role === "acceptance");
    assert.equal(byId.get(acceptance.source).parent, relay.id);
    assert.equal(acceptance.target, "sender");
    const delivery = model.edges.find(e => e.role === "delivery");
    assert.equal(delivery.source, "destination-queue");
    assert.equal(delivery.target, "receiver");
    assert.notEqual(acceptance.id, delivery.id);
  }
});

test("Request/reply routes a fresh correlated reply through Alice's separate native queue", () => {
  for (const layout of ["wide", "compact"]) {
    const model = getDiagramModel("request-reply", layout);
    const request = model.edges.find(e => e.role === "send");
    const reply = model.edges.find(e => e.role === "reply");
    const matching = model.edges.find(e => e.role === "reply-delivery");
    assert.equal(request.source, "sender"); assert.equal(request.target, "destination-queue");
    assert.equal(reply.source, "receiver"); assert.equal(reply.target, "reply-queue");
    assert.equal(reply.freshId, true); assert.equal(reply.replyTo, "request");
    assert.equal(matching.source, "reply-queue"); assert.equal(matching.target, "sender");
    assert.equal(model.nodes.find(n => n.id === "reply-queue").parent, "relay");
  }
  for (const kind of ["architecture", "send"]) assert.equal(getDiagramModel(kind, "wide").edges.some(e => e.role === "reply"), false);
});

test("Compact and wide layouts preserve readable node sizes, bounds and sibling separation", () => {
  for (const kind of kinds) for (const [layout, widths] of [["compact", [280, 320, 375, 650]], ["wide", [680, 900, 1024]]]) {
    for (const width of widths) {
      const model = getDiagramModel(kind, layout, width);
      assert.equal(model.width, width);
      const canvas = { x: 0, y: 0, width: model.width, height: model.height };
      for (const node of model.nodes) {
        assert.ok(inside(node, canvas), `${kind}/${width}: ${node.id} in bounds`);
        assert.ok(node.width >= 140 && node.height >= 70);
      }
      for (const [i, a] of model.nodes.entries()) for (const b of model.nodes.slice(i + 1)) {
        if (a.parent === b.id || b.parent === a.id) continue;
        assert.equal(overlaps(a, b), false, `${kind}/${width}: ${a.id} overlaps ${b.id}`);
      }
      for (const edge of model.edges) for (const vertex of edge.vertices ?? []) {
        assert.ok(vertex.x >= 0 && vertex.x <= model.width && vertex.y >= 0 && vertex.y <= model.height);
      }
    }
  }
});

test("Each call returns independent scene data", () => {
  const first = getDiagramModel("send", "wide");
  first.nodes[0].label = "changed"; first.edges.length = 0;
  const second = getDiagramModel("send", "wide");
  assert.notEqual(second.nodes[0].label, "changed"); assert.ok(second.edges.length > 0);
});
