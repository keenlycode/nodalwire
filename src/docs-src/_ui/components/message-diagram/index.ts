import { Base } from "../base";
import { isDiagramKind } from "./model";
import { messageDiagramStyles } from "./styles";
export type { DiagramKind } from "./model";

/** Progressive static diagram: caller-authored native figure/text is never replaced. */
export class MessageDiagram extends Base {
  static { this.css = messageDiagramStyles; }
  static observedAttributes = ["kind"];

  static override define(tagName: string): void {
    super.define(tagName);
    // Adapter installs class CSS after upgrading authored hosts. Their first
    // callbacks can see inline/default figure widths; retry once registration
    // has synchronously installed CSS, without waiting for a rendering frame.
    // Background documents may not receive ResizeObserver delivery yet.
    for (const host of document.querySelectorAll<MessageDiagram>(tagName)) {
      if (host instanceof this) void host.#update();
    }
  }
  #observer?: ResizeObserver;
  #visual?: HTMLDivElement;
  #dispose?: () => void;
  #revision = 0;
  #key?: string;

  override connectedCallback(): void {
    super.connectedCallback();
    if (typeof ResizeObserver !== "undefined" && !this.#observer) {
      this.#observer = new ResizeObserver(() => { void this.#update(); });
      this.#observer.observe(this);
    }
    void this.#update();
  }

  disconnectedCallback(): void {
    this.#observer?.disconnect(); this.#observer = undefined;
    this.#clear();
    // Adapter has no disconnectedCallback; native content stays caller-owned.
  }

  attributeChangedCallback(): void {
    if (this.isConnected) void this.#update();
  }

  #clear(): void {
    ++this.#revision;
    this.#dispose?.(); this.#dispose = undefined;
    this.#visual?.remove(); this.#visual = undefined;
    this.#key = undefined;
  }

  async #update(): Promise<void> {
    if (!this.isConnected) return;
    const figures = this.querySelectorAll<HTMLElement>(":scope > figure");
    const figure = figures.length === 1 ? figures[0] : undefined;
    const kind = this.getAttribute("kind");
    const width = Math.floor(figure?.clientWidth ?? 0);
    if (!figure || !figure.querySelector(":scope > figcaption") || !isDiagramKind(kind) || width < 280) {
      this.#clear(); this.dataset.diagramState = "fallback"; return;
    }
    const key = `${kind}:${width}`;
    if (key === this.#key) return;
    this.#clear(); this.#key = key;
    const revision = this.#revision;
    this.dataset.diagramState = "loading";
    try {
      const { renderDiagram } = await import("./render");
      if (revision !== this.#revision || !this.isConnected) return;
      const visual = document.createElement("div");
      visual.className = "message-diagram-visual";
      visual.setAttribute("aria-hidden", "true");
      figure.querySelector(":scope > figcaption")!.after(visual);
      this.#visual = visual;
      this.#dispose = renderDiagram(visual, kind, width);
      this.dataset.diagramState = "ready";
    } catch {
      if (revision !== this.#revision) return;
      this.#dispose?.(); this.#dispose = undefined;
      this.#visual?.remove(); this.#visual = undefined;
      this.dataset.diagramState = "fallback";
    }
  }
}

/** Importing never registers; coordinator's root entry calls this explicitly. */
export function registerMessageDiagram(): void {
  MessageDiagram.define("nw-message-diagram");
}
