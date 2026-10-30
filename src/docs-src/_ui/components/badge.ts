import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

/** A static text label, not an interactive control or live region. */
export class Badge extends Base {
  static { this.css = componentStyles.badge; }
  static create(options: { text: string }): Badge {
    if (!options || typeof options.text !== "string" || !options.text.trim()) throw new TypeError("Badge text must be nonempty text");
    const host = new this(); const span = document.createElement("span");
    span.textContent = options.text; host.append(span); return host;
  }
}
