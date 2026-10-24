/** Progressive design-only presentation. SSR links remain usable without scripts. */
export function enhanceDesignNavigation(): void {
  const host = document.querySelector<HTMLElement>("[data-design-navigation]");
  if (!host || host.dataset.enhanced) return;
  const pin = host.querySelector<HTMLElement>("nw-button-pin");
  const button = pin?.querySelector<HTMLButtonElement>("button");
  const panel = host.querySelector<HTMLElement>("#design-menu-panel");
  if (!pin || !button || !panel) return;
  host.dataset.enhanced = "true";
  panel.hidden = true;
  pin.hidden = false;
  button.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    button.setAttribute("aria-expanded", String(!panel.hidden));
    button.setAttribute("aria-label", panel.hidden ? "Open design navigation" : "Close design navigation");
  });
  host.addEventListener("keydown", event => {
    if (event.key !== "Escape" || panel.hidden) return;
    event.preventDefault();
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Open design navigation");
    button.focus();
  });
}
