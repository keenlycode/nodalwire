import { Adapter } from "@devcapsule/adapter";
import { componentStyles } from "./resolved-styles";

/** Actual Adapter foundation; native-control/content ownership stays with callers. */
export class Base extends Adapter {
  static { this.css = componentStyles.base; }
  /** Register this class once without replacing another component's definition. */
  static define(tagName: string): void {
    const existing = customElements.get(tagName);
    if (existing && existing !== this) throw new Error(`Foreign definition for ${tagName}`);
    if (!existing) super.define(tagName);
  }
}
