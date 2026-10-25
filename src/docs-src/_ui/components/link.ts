import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

export type LinkOptions = { label: string; href: string };
/** Native anchor attributes remain authoritative; no host focus or role. */
export class Link extends Base {
  static { this.css = componentStyles.link; }
  get anchor(): HTMLAnchorElement {
    const anchors = this.querySelectorAll<HTMLAnchorElement>(":scope > a");
    if (anchors.length !== 1) throw new TypeError("Link requires exactly one direct native anchor");
    return anchors[0];
  }
  static create(options: LinkOptions): Link {
    if (!options || typeof options.label !== "string" || !options.label.trim()) throw new TypeError("Link label must be nonempty text");
    if (typeof options.href !== "string" || !options.href.trim()) throw new TypeError("Link href must be nonempty text");
    const url = new URL(options.href, document.baseURI);
    if (!["http:", "https:", "mailto:", "tel:"].includes(url.protocol)) throw new TypeError("Unsupported link protocol");
    const host = new this(); const anchor = document.createElement("a");
    anchor.setAttribute("href", options.href); anchor.textContent = options.label;
    host.append(anchor); return host;
  }
}
