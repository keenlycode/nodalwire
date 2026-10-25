import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

export type ButtonOptions = { label: string; type?: "button" | "submit" | "reset"; disabled?: boolean };
export class Button extends Base {
  static { this.css = componentStyles.button; }
  get button(): HTMLButtonElement {
    const buttons = this.querySelectorAll<HTMLButtonElement>(":scope > button");
    if (buttons.length !== 1) throw new TypeError("Button requires exactly one direct native button");
    return buttons[0];
  }
  static create(options: ButtonOptions): Button {
    if (!options || typeof options.label !== "string" || !options.label.trim()) throw new TypeError("Button label must be nonempty text");
    const type = options.type ?? "button";
    if (!["button", "submit", "reset"].includes(type)) throw new TypeError("Invalid button type");
    if (options.disabled !== undefined && typeof options.disabled !== "boolean") throw new TypeError("disabled must be boolean");
    const host = new this();
    const native = document.createElement("button");
    native.type = type; native.textContent = options.label; native.disabled = options.disabled ?? false;
    host.append(native); return host;
  }
}
