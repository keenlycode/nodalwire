import { Base } from "./base";
import { IconButton } from "./icon-button";
import { componentStyles } from "./resolved-styles";

const languages: Record<string, { id: "python" | "javascript"; label: string }> = {
  python: { id: "python", label: "Python" }, py: { id: "python", label: "Python" },
  javascript: { id: "javascript", label: "JavaScript" }, js: { id: "javascript", label: "JavaScript" },
};
const languageInfo = (value: string) => Object.hasOwn(languages, value) ? languages[value] : undefined;

/** Native pre/code remains canonical; token spans preserve its exact text. */
export class CodeBlock extends Base {
  static { this.css = componentStyles.codeBlock; }
  static observedAttributes = ["filename", "language"];
  #action?: IconButton;
  #labels?: HTMLElement;
  #status?: HTMLOutputElement;
  #pending = false;
  #revision = 0;
  #highlighted?: { code: HTMLElement; text: string; language: string };
  get code(): HTMLElement {
    const code = this.querySelectorAll<HTMLElement>(":scope > pre > code");
    if (code.length !== 1) throw new TypeError("CodeBlock requires exactly one pre/code");
    return code[0];
  }
  static create(options: { text: string; filename?: string; language?: string }): CodeBlock {
    if (!options || typeof options.text !== "string") throw new TypeError("Code text must be a string");
    for (const key of ["filename", "language"] as const) {
      if (options[key] !== undefined && typeof options[key] !== "string") throw new TypeError(`${key} must be a string`);
    }
    const host = new this(); const pre = document.createElement("pre");
    pre.tabIndex = 0; pre.setAttribute("aria-label", "Code example");
    const code = document.createElement("code"); code.textContent = options.text;
    pre.append(code); host.append(pre);
    if (options.filename !== undefined) host.setAttribute("filename", options.filename);
    if (options.language !== undefined) host.setAttribute("language", options.language);
    return host;
  }
  override connectedCallback(): void {
    super.connectedCallback();
    this.code;
    if (!this.#action) {
      const header = this.querySelector<HTMLElement>(":scope > .code-block-header") ?? document.createElement("div");
      header.className = "code-block-header";
      const labels = this.#labels = header.querySelector<HTMLElement>(".code-block-labels") ?? document.createElement("span");
      labels.className = "code-block-labels";
      const action = this.#action = IconButton.create({ label: "Copy code" });
      const status = this.#status = document.createElement("output");
      status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
      action.button.addEventListener("click", () => { void this.copy(); });
      header.replaceChildren(labels, action); this.prepend(header); this.append(status);
    }
    this.updateLabels();
    void this.highlight();
  }
  attributeChangedCallback(name: string): void {
    if (!this.#action) return;
    this.updateLabels();
    if (name === "language") void this.highlight();
  }
  private updateLabels(): void {
    const filename = this.getAttribute("filename") ?? "";
    const language = this.getAttribute("language") ?? "";
    this.#labels!.replaceChildren();
    for (const [className, text] of [
      ["code-block-filename", filename],
      ["code-block-language", languageInfo(language.trim().toLowerCase())?.label ?? language],
    ]) {
      if (!text.trim()) continue;
      const label = document.createElement("span"); label.className = className; label.textContent = text;
      this.#labels!.append(label);
    }
  }
  /** Call after changing authored code text; attribute changes refresh automatically. */
  async highlight(): Promise<void> {
    const revision = ++this.#revision;
    const code = this.code, text = code.textContent ?? "";
    const language = languageInfo((this.getAttribute("language") ?? "").trim().toLowerCase())?.id;
    if (!language) {
      if (this.#highlighted?.code === code) code.textContent = text;
      this.#highlighted = undefined; this.dataset.highlight = "plain"; return;
    }
    if (this.#highlighted?.code === code && this.#highlighted.text === text && this.#highlighted.language === language) {
      this.dataset.highlight = "ready"; return;
    }
    // Remove a previous language's presentation before starting a different request.
    if (this.#highlighted?.code === code) code.textContent = text;
    this.#highlighted = undefined; this.dataset.highlight = "loading";
    try {
      const { tokenizeCode } = await import("./code-highlight");
      const tokens = await tokenizeCode(text, language);
      if (revision !== this.#revision || !this.isConnected || this.code !== code || code.textContent !== text) return;
      const fragment = document.createDocumentFragment(); let cursor = 0;
      for (const token of tokens) {
        // Preserve original separators (including CRLF), whitespace and final newlines.
        fragment.append(document.createTextNode(text.slice(cursor, token.offset)));
        const span = document.createElement("span"); span.textContent = token.content;
        if (token.color) span.style.color = token.color;
        fragment.append(span); cursor = token.offset + token.content.length;
      }
      fragment.append(document.createTextNode(text.slice(cursor)));
      if (fragment.textContent !== text) throw new Error("Highlighting must preserve code text");
      code.replaceChildren(fragment); this.#highlighted = { code, text, language };
      this.dataset.highlight = "ready";
    } catch {
      if (revision === this.#revision) this.dataset.highlight = "plain";
    }
  }
  private async copy(): Promise<void> {
    if (this.#pending) return;
    this.#pending = true;
    this.#status!.textContent = "Copying…";
    const text = this.code.textContent ?? "";
    try {
      if (!window.isSecureContext || !navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(text);
      this.#status!.textContent = "Code copied.";
    } catch {
      this.#status!.textContent = "Could not copy. Select and copy the code manually.";
    } finally { this.#pending = false; }
  }
}
