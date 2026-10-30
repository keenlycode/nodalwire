import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

/** Native disclosure works without JS; enhancement adds Escape and explicit state. */
export class BottomNavigation extends Base {
  static { this.css = componentStyles.bottomNavigation; }
  #bound = false;
  override connectedCallback(): void {
    super.connectedCallback();
    if (this.#bound) return;
    const details = this.querySelector<HTMLDetailsElement>(":scope > details");
    const summary = details?.querySelector<HTMLElement>(":scope > summary");
    if (!details || !summary) throw new TypeError("BottomNavigation requires native details/summary");
    const sync = () => summary.setAttribute("aria-expanded", String(details.open));
    sync();
    details.addEventListener("toggle", sync);
    // Native toggle events are queued; reflect open-attribute changes in the
    // mutation microtask too, including scripted/native disclosure changes.
    new MutationObserver(sync).observe(details, { attributes: true, attributeFilter: ["open"] });
    this.addEventListener("keydown", event => {
      if (event.key !== "Escape" || !details.open) return;
      event.preventDefault(); details.open = false; sync(); summary.focus();
    });
    this.#bound = true;
  }
}
