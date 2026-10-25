import { Button, Card, IconButton, Link, Badge, InlineCode, registerComponents } from "../../_ui/components";
import { enhanceDesignNavigation } from "../_include/navigation";
registerComponents();
enhanceDesignNavigation();
const factoryHost = document.querySelector("#factory");
if (factoryHost) {
  const factory = Button.create({ label: "Factory-created action" }); factory.id = "factory-button";
  factoryHost.append(factory);
}
const cardHost = document.querySelector("#factory-card");
if (cardHost) {
  const heading = document.createElement("h3"); heading.textContent = "Factory-created Card";
  const paragraph = document.createElement("p"); paragraph.textContent = "The factory preserves native nodes. Registration adds composition helpers, not replacement browser semantics.";
  cardHost.append(Card.create({ children: [heading, paragraph, Button.create({ label: "Composed action" })] }));
}
const iconHost = document.querySelector("#icon-examples");
if (iconHost) {
  const icon = IconButton.create({ label: "Example copy icon action" });
  icon.button.addEventListener("click", () => { const output = document.querySelector("#icon-result"); if (output) output.textContent = "Icon action activated (no clipboard access)."; });
  iconHost.append(icon, IconButton.create({ label: "Disabled copy action", disabled: true }));
}
document.querySelector("#factory-link")?.append(Link.create({ label: "Back to Button examples", href: document.querySelector("#buttons") ? "#buttons" : "../button/" }));
document.querySelector("#factory-badge")?.append(Badge.create({ text: "Factory label" }));
document.querySelector("#factory-inline-code")?.append(InlineCode.create({ text: "const literal = '<safe> & text';  // preserved spacing" }));
document.querySelector("#stack-visibility")?.addEventListener("click", event => {
  const stack = document.querySelector<HTMLElement>("#standalone-stack");
  if (!stack) return;
  stack.hidden = !stack.hidden;
  (event.currentTarget as HTMLButtonElement).setAttribute("aria-expanded", String(!stack.hidden));
});
let count = 0;
document.querySelectorAll("nw-button > button:not([type=submit]):not([type=reset])").forEach(button => button.addEventListener("click", () => { const output = document.querySelector("#action-result"); if (output) output.textContent = `Activated ${++count} time(s).`; }));
document.querySelector("#native-form")?.addEventListener("submit", event => {
  event.preventDefault(); const submitter = (event as SubmitEvent).submitter as HTMLButtonElement;
  const output = document.querySelector("#form-result");
  if (output) output.textContent = `Local submit: ${new FormData(event.currentTarget as HTMLFormElement).get("example")}; ${submitter.name}=${submitter.value}`;
});
document.querySelector("#native-form")?.addEventListener("reset", () => { const output = document.querySelector("#form-result"); if (output) output.textContent = "Reset to Draft."; });
