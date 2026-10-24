import { Base } from "./base";
import { IconButton } from "./icon-button";
import { componentStyles } from "./resolved-styles";

/** Authored pre/code is canonical; enhancement never parses or rewrites its text. */
export class CodeBlock extends Base {
  static { this.css = componentStyles.codeBlock; }
  #action?: IconButton;
  #status?: HTMLOutputElement;
  #pending = false;
  get code(): HTMLElement {
    const code = this.querySelectorAll<HTMLElement>(":scope > pre > code");
    if (code.length !== 1) throw new TypeError("CodeBlock requires exactly one pre/code");
    return code[0];
  }
  static create(options: { text: string }): CodeBlock {
    if (!options || typeof options.text !== "string") throw new TypeError("Code text must be a string");
    const host = new this(); const pre = document.createElement("pre");
    pre.tabIndex = 0; pre.setAttribute("aria-label", "Code example");
    const code = document.createElement("code"); code.textContent = options.text;
    pre.append(code); host.append(pre); return host;
  }
  override connectedCallback(): void {
    super.connectedCallback();
    this.code;
    if (this.#action) return;
    const action = this.#action = IconButton.create({ label: "Copy code" });
    const status = this.#status = document.createElement("output");
    status.setAttribute("role", "status"); status.setAttribute("aria-live", "polite");
    status.textContent = "Ready to copy.";
    action.button.addEventListener("click", () => { void this.copy(); });
    this.append(action, status);
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
