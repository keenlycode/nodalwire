/** DOM-free scene descriptions; JointJS is only the browser presentation. */
export type DiagramKind = "architecture" | "send" | "request-reply";
export type DiagramLayout = "wide" | "compact";
export type DiagramNode = {
  id: string;
  role: "application" | "relay" | "native-queue";
  label: string;
  parent?: string;
  x: number; y: number; width: number; height: number;
};
export type DiagramEdge = {
  id: string;
  role: "send" | "delivery" | "acceptance" | "reply" | "reply-delivery";
  source: string; target: string; label: string;
  sourceAnchor: "top" | "bottom" | "left" | "right";
  targetAnchor: "top" | "bottom" | "left" | "right";
  vertices?: Array<{ x: number; y: number }>;
  labelDistance?: number;
  labelOffset?: { x: number; y: number };
  freshId?: boolean;
  replyTo?: "request";
};
export type DiagramModel = {
  kind: DiagramKind; layout: DiagramLayout; width: number; height: number;
  nodes: DiagramNode[]; edges: DiagramEdge[];
  acceptanceBoundary: "relay-native-destination-queue";
};

export function isDiagramKind(value: unknown): value is DiagramKind {
  return value === "architecture" || value === "send" || value === "request-reply";
}

/** Fixed, readable layouts, not a graph-layout engine or interactive simulator. */
export function getDiagramModel(kind: DiagramKind, layout: DiagramLayout, requestedWidth?: number): DiagramModel {
  if (!isDiagramKind(kind)) throw new RangeError("Unknown message diagram kind");
  if (layout !== "wide" && layout !== "compact") throw new RangeError("Unknown diagram layout");
  if (requestedWidth !== undefined && (!Number.isFinite(requestedWidth) || requestedWidth <= 0)) {
    throw new RangeError("Diagram width must be finite and positive");
  }
  const compact = layout === "compact", reply = kind === "request-reply";
  const width = Math.max(compact ? 280 : 680, requestedWidth ?? (compact ? 360 : 900));
  const nodes: DiagramNode[] = [], edges: DiagramEdge[] = [];
  const node = (id: string, role: DiagramNode["role"], label: string, x: number, y: number, w: number, h: number, parent?: string) => {
    nodes.push({ id, role, label, x, y, width: w, height: h, ...(parent ? { parent } : {}) });
  };
  let height: number;
  if (compact) {
    const appWidth = 164, queueWidth = Math.min(200, width - 96), center = width / 2;
    height = reply ? 990 : 670;
    node("sender", "application", reply ? "Alice\nRequester" : "Alice\nSending application", center - appWidth / 2, 18, appWidth, 74);
    node("relay", "relay", "Loopback relay", 12, 206, width - 24, reply ? 530 : 236);
    node("destination-queue", "native-queue", "Bob's native\ndestination queue", center - queueWidth / 2, 272, queueWidth, 76, "relay");
    node("receiver", "application", reply ? "Bob\nService application" : "Bob\nReceiving application", center - appWidth / 2, reply ? 886 : 570, appWidth, 78);
    edges.push({ id: "outbound", role: "send", source: "sender", target: "destination-queue", label: reply ? "1. Request" : "1. Send to Bob", sourceAnchor: "bottom", targetAnchor: "top", labelDistance: .44 });
    // Receipt returns from the relay's queue boundary, not from Bob's app.
    edges.push({ id: "accepted", role: "acceptance", source: "destination-queue", target: "sender", label: "Send\naccepted", sourceAnchor: "left", targetAnchor: "left", vertices: [{ x: 30, y: 310 }, { x: 30, y: 55 }], labelDistance: .48 });
    edges.push({ id: "delivered", role: "delivery", source: "destination-queue", target: "receiver", label: "2. Receive later;\nprocess separately", sourceAnchor: "right", targetAnchor: "right", vertices: [{ x: width - 32, y: 310 }, { x: width - 32, y: reply ? 925 : 610 }], labelDistance: reply ? .78 : .64, labelOffset: { x: -72, y: 0 } });
    if (reply) {
      node("reply-queue", "native-queue", "Alice's native\ndestination queue", center - queueWidth / 2, 546, queueWidth, 76, "relay");
      edges.push({ id: "reply", role: "reply", source: "receiver", target: "reply-queue", label: "3. Reply", sourceAnchor: "top", targetAnchor: "bottom", freshId: true, replyTo: "request" });
      edges.push({ id: "matched", role: "reply-delivery", source: "reply-queue", target: "sender", label: "4. Matching\nreply", sourceAnchor: "left", targetAnchor: "top", vertices: [{ x: 58, y: 584 }, { x: 58, y: 4 }, { x: center, y: 4 }], labelDistance: .46 });
    }
  } else {
    const appWidth = 154, relayWidth = Math.max(260, width * .34), relayX = (width - relayWidth) / 2;
    const queueWidth = relayWidth - 64, queueX = relayX + 32;
    height = reply ? 570 : 440;
    node("sender", "application", reply ? "Alice\nRequester" : "Alice\nSending application", 12, 190, appWidth, 84);
    node("relay", "relay", "Loopback relay", relayX, 92, relayWidth, reply ? 420 : 220);
    node("destination-queue", "native-queue", "Bob's native\ndestination queue", queueX, 166, queueWidth, 78, "relay");
    node("receiver", "application", reply ? "Bob\nService application" : "Bob\nReceiving application", width - appWidth - 12, 190, appWidth, 84);
    edges.push({ id: "outbound", role: "send", source: "sender", target: "destination-queue", label: reply ? "1. Request" : "1. Send\nto Bob", sourceAnchor: "right", targetAnchor: "left" });
    edges.push({ id: "accepted", role: "acceptance", source: "destination-queue", target: "sender", label: "Send accepted", sourceAnchor: "top", targetAnchor: "top", vertices: [{ x: width / 2, y: 44 }, { x: 89, y: 44 }], labelDistance: .55 });
    edges.push({ id: "delivered", role: "delivery", source: "destination-queue", target: "receiver", label: "2. Receive later;\nprocess separately", sourceAnchor: "right", targetAnchor: "left" });
    if (reply) {
      node("reply-queue", "native-queue", "Alice's native\ndestination queue", queueX, 390, queueWidth, 78, "relay");
      edges.push({ id: "reply", role: "reply", source: "receiver", target: "reply-queue", label: "3. Reply", sourceAnchor: "bottom", targetAnchor: "right", vertices: [{ x: width - 89, y: 429 }], freshId: true, replyTo: "request" });
      edges.push({ id: "matched", role: "reply-delivery", source: "reply-queue", target: "sender", label: "4. Matching reply", sourceAnchor: "left", targetAnchor: "bottom", vertices: [{ x: 89, y: 429 }] });
    }
  }
  return { kind, layout, width, height, nodes, edges, acceptanceBoundary: "relay-native-destination-queue" };
}
