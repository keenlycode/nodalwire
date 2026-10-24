import { Button, type ButtonOptions } from "./button";
import { componentStyles } from "./resolved-styles";
import { copySVG } from "./gnomicon-copy";

/** Native Button mechanics with a deterministic copy glyph and explicit name. */
export class IconButton extends Button {
  static { this.css = componentStyles.iconButton; }
  static override create(options: ButtonOptions): IconButton {
    const host = super.create(options) as IconButton;
    host.button.setAttribute("aria-label", options.label);
    host.button.replaceChildren(copyIcon());
    return host;
  }
}
function copyIcon(): SVGSVGElement {
  // This is the vetted, fixed official asset, never caller-provided markup.
  const parsed = new DOMParser().parseFromString(copySVG, "image/svg+xml");
  const svg = document.importNode(parsed.documentElement, true) as unknown as SVGSVGElement;
  svg.setAttribute("aria-hidden", "true"); svg.setAttribute("focusable", "false");
  return svg;
}
