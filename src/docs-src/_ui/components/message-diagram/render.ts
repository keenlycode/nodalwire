import { dia, shapes } from "@joint/core";
import { getDiagramModel, type DiagramKind } from "./model";

/** Called only in a real browser; no headless SVG or server-side DOM promise. */
export function renderDiagram(container: HTMLElement, kind: DiagramKind, width: number): () => void {
  const model = getDiagramModel(kind, width < 680 ? "compact" : "wide", width);
  const styles = getComputedStyle(container);
  const color = (role: string, fallback: string) => styles.getPropertyValue(`--${role}`).trim() || fallback;
  const ink = color("ink", "#1e1e1e"), surface = color("surface", "#ffffff");
  const muted = color("muted", "#505050"), accent = color("accent", "#1c71d8");
  const graph = new dia.Graph({}, { cellNamespace: shapes });
  const paper = new dia.Paper({
    el: container,
    model: graph,
    width: model.width,
    height: model.height,
    cellViewNamespace: shapes,
    interactive: false,
    async: false,
    frozen: true,
    background: { color: surface },
  });
  try {
    const elements = new Map<string, shapes.standard.Rectangle>();
    for (const node of model.nodes) {
      const relay = node.role === "relay", queue = node.role === "native-queue";
      const element = new shapes.standard.Rectangle({ id: node.id, z: relay ? 1 : 2 });
      element.position(node.x, node.y);
      element.resize(node.width, node.height);
      element.attr({
        root: { cursor: "default", "data-diagram-node": node.id, "data-node-role": node.role },
        body: {
          fill: surface, stroke: queue ? accent : ink, strokeWidth: relay ? 1.5 : 2,
          strokeDasharray: relay ? "7 4" : "none", rx: queue ? 4 : 10, ry: queue ? 4 : 10,
        },
        label: {
          text: node.label, fill: ink, fontSize: 14, fontFamily: "system-ui, sans-serif",
          fontWeight: relay ? 600 : 400,
          ...(relay ? { y: 25 } : {}),
        },
      });
      element.addTo(graph);
      elements.set(node.id, element);
    }
    for (const node of model.nodes) {
      if (node.parent) elements.get(node.parent)!.embed(elements.get(node.id)!);
    }
    for (const edge of model.edges) {
      const receipt = edge.role === "acceptance";
      const link = new shapes.standard.Link({ id: edge.id, z: 3 });
      link.source({ id: edge.source, anchor: { name: edge.sourceAnchor } });
      link.target({ id: edge.target, anchor: { name: edge.targetAnchor } });
      if (edge.vertices) link.vertices(edge.vertices);
      link.connector("rounded", { radius: 8 });
      link.attr({
        root: { "data-diagram-edge": edge.id, "data-edge-role": edge.role },
        line: {
          stroke: receipt ? muted : accent, strokeWidth: receipt ? 1.5 : 2,
          strokeDasharray: receipt ? "5 4" : "none",
          targetMarker: { type: "path", d: "M 8 -4 0 0 8 4 z", fill: receipt ? muted : accent, stroke: "none" },
        },
      });
      link.appendLabel({
        position: { distance: edge.labelDistance ?? .5, offset: edge.labelOffset ?? 0 },
        attrs: {
          text: { text: edge.label, fill: ink, fontSize: 13, fontFamily: "system-ui, sans-serif" },
          rect: { fill: surface, stroke: "none", rx: 3, ry: 3 },
        },
      });
      link.addTo(graph);
    }
    paper.unfreeze();
    // The native figure is the accessible equivalent. SVG adds no focus surface.
    container.querySelector("svg")?.setAttribute("focusable", "false");
    container.dataset.layout = model.layout;
    return () => { paper.remove(); graph.clear(); };
  } catch (error) {
    paper.remove(); graph.clear();
    throw error;
  }
}
