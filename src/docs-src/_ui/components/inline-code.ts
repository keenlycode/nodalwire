import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

/** Inline native code, with literal text and wrapping rather than HTML parsing. */
export class InlineCode extends Base {
  static { this.css = componentStyles.inlineCode; }
  static create(options: { text: string }): InlineCode {
    if (!options || typeof options.text !== "string") throw new TypeError("Inline code text must be a string");
    const host = new this(); const code = document.createElement("code");
    code.textContent = options.text; host.append(code); return host;
  }
}
