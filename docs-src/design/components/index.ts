import { Button, Card, registerComponents } from "../../_ui/components";
registerComponents();
const factory = Button.create({ label: "Factory-created action" }); factory.id = "factory-button";
document.querySelector("#factory")!.append(factory);
const heading = document.createElement("h3"); heading.textContent = "Factory-created Card";
const paragraph = document.createElement("p"); paragraph.textContent = "The factory preserves native nodes. Registration adds composition helpers, not replacement browser semantics.";
document.querySelector("#factory-card")!.append(Card.create({ children: [heading, paragraph, Button.create({ label: "Composed action" })] }));
let count = 0;
document.querySelectorAll("nw-button > button:not([type=submit]):not([type=reset])").forEach(button => button.addEventListener("click", () => { document.querySelector("#action-result")!.textContent = `Activated ${++count} time(s).`; }));
document.querySelector("#native-form")!.addEventListener("submit", event => {
  event.preventDefault(); const submitter = (event as SubmitEvent).submitter as HTMLButtonElement;
  document.querySelector("#form-result")!.textContent = `Local submit: ${new FormData(event.currentTarget as HTMLFormElement).get("example")}; ${submitter.name}=${submitter.value}`;
});
document.querySelector("#native-form")!.addEventListener("reset", () => { document.querySelector("#form-result")!.textContent = "Reset to Draft."; });
