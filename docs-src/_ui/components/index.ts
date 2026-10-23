import { Button } from "./button";
import { Card } from "./card";
export { Button, Card };
export function registerComponents(): void {
  for (const [tag, component] of [["nw-button", Button], ["nw-card", Card]] as const) {
    const existing = customElements.get(tag);
    if (existing && existing !== component) throw new Error(`Foreign definition for ${tag}`);
    if (!existing) customElements.define(tag, component);
  }
}
