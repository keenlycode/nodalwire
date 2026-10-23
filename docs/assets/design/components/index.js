// docs-src/_ui/components/button.ts
var Button = class extends HTMLElement {
  get button() {
    const buttons = this.querySelectorAll(":scope > button");
    if (buttons.length !== 1) throw new TypeError("Button requires exactly one direct native button");
    return buttons[0];
  }
  static create(options) {
    if (!options || typeof options.label !== "string" || !options.label.trim()) throw new TypeError("Button label must be nonempty text");
    const type = options.type ?? "button";
    if (!["button", "submit", "reset"].includes(type)) throw new TypeError("Invalid button type");
    if (options.disabled !== void 0 && typeof options.disabled !== "boolean") throw new TypeError("disabled must be boolean");
    const host = new this();
    const native = document.createElement("button");
    native.type = type;
    native.textContent = options.label;
    native.disabled = options.disabled ?? false;
    host.append(native);
    return host;
  }
};

// docs-src/_ui/components/card.ts
var Card = class extends HTMLElement {
  static create(options = {}) {
    const children = [...options.children ?? []];
    if (children.some((child) => typeof child !== "string" && !(child instanceof Node))) throw new TypeError("Card children must be nodes or text");
    const card = new this();
    card.append(...children);
    return card;
  }
};

// docs-src/_ui/components/index.ts
function registerComponents() {
  for (const [tag, component] of [["nw-button", Button], ["nw-card", Card]]) {
    const existing = customElements.get(tag);
    if (existing && existing !== component) throw new Error(`Foreign definition for ${tag}`);
    if (!existing) customElements.define(tag, component);
  }
}

// docs-src/design/components/index.ts
registerComponents();
var factory = Button.create({ label: "Factory-created action" });
factory.id = "factory-button";
document.querySelector("#factory").append(factory);
var heading = document.createElement("h3");
heading.textContent = "Factory-created Card";
var paragraph = document.createElement("p");
paragraph.textContent = "The factory preserves native nodes. Registration adds composition helpers, not replacement browser semantics.";
document.querySelector("#factory-card").append(Card.create({ children: [heading, paragraph, Button.create({ label: "Composed action" })] }));
var count = 0;
document.querySelectorAll("nw-button > button:not([type=submit]):not([type=reset])").forEach((button) => button.addEventListener("click", () => {
  document.querySelector("#action-result").textContent = `Activated ${++count} time(s).`;
}));
document.querySelector("#native-form").addEventListener("submit", (event) => {
  event.preventDefault();
  const submitter = event.submitter;
  document.querySelector("#form-result").textContent = `Local submit: ${new FormData(event.currentTarget).get("example")}; ${submitter.name}=${submitter.value}`;
});
document.querySelector("#native-form").addEventListener("reset", () => {
  document.querySelector("#form-result").textContent = "Reset to Draft.";
});
