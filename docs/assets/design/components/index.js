// <define:__NW_COMPONENT_STYLES__>
var define_NW_COMPONENT_STYLES_default = { base: "box-sizing:border-box; font-family:system-ui, sans-serif; line-height:1.5; color:#241f31;", button: "display:inline-flex; vertical-align:middle; max-width:100%;\n      & > button { box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; min-height:2.25rem; max-width:100%; margin:0; border:1px solid #1a5fb4; border-radius:0.75rem; padding:0.5rem 1rem; background:#1a5fb4; color:#ffffff; font:inherit; font-size:.875rem; font-weight:500; line-height:1.25; text-align:center; overflow-wrap:anywhere; cursor:pointer; }\n      & > button:hover:not(:disabled) { background:#241f31; border-color:#241f31; }\n      & > button:focus-visible { outline:2px solid #1a5fb4; outline-offset:3px; }\n      & > button:disabled { background:#deddda; border-color:#c0bfbc; color:#5e5c64; cursor:not-allowed; }", card: "display:grid; gap:1rem; padding:1.5rem; border:1px solid #c0bfbc; border-radius:0.75rem; background:#ffffff; color:#241f31; min-width:0; overflow-wrap:anywhere;\n      & > :first-child { margin-top:0; } & > :last-child { margin-bottom:0; }" };

// tools/docs/node_modules/.pnpm/@jsr+devcapsule__adapter@https+++npm.jsr.io+~+11+@jsr+devcapsule__adapter+4.0.0.tgz/node_modules/@jsr/devcapsule__adapter/src/util.js
function uuid() {
  const g = typeof globalThis !== "undefined" ? globalThis : {};
  const c = g.crypto || g.msCrypto;
  if (c && typeof c.randomUUID === "function") {
    return c.randomUUID();
  }
  if (c && typeof c.getRandomValues === "function") {
    const bytes = new Uint8Array(16);
    c.getRandomValues(bytes);
    bytes[6] = bytes[6] & 15 | 64;
    bytes[8] = bytes[8] & 63 | 128;
    const hex = Array.from(bytes, (b) => b.toString(16).padStart(2, "0")).join("");
    return hex.slice(0, 8) + "-" + hex.slice(8, 12) + "-" + hex.slice(12, 16) + "-" + hex.slice(16, 20) + "-" + hex.slice(20);
  }
  const counter = uuid._ctr = (uuid._ctr || 0) + 1;
  const time = Date.now().toString(36);
  const rand = Math.random().toString(36).slice(2, 10);
  return `${time}-${rand}-${counter.toString(36)}`;
}

// tools/docs/node_modules/.pnpm/@jsr+devcapsule__adapter@https+++npm.jsr.io+~+11+@jsr+devcapsule__adapter+4.0.0.tgz/node_modules/@jsr/devcapsule__adapter/src/css.js
var css = String.raw;

// tools/docs/node_modules/.pnpm/@jsr+devcapsule__adapter@https+++npm.jsr.io+~+11+@jsr+devcapsule__adapter+4.0.0.tgz/node_modules/@jsr/devcapsule__adapter/src/adapter.js
var AdapterClassController = class {
  /**
   * Reference to the Adapter constructor that owns this controller.
   *
   * Notes
   * -----
   * Set internally by AdapterMixin when the subclass is first accessed.
   */
  adapterClass;
  /**
   * Constructable stylesheet that holds class-level CSS rules.
   *
   * Notes
   * -----
   * Added to `document.adoptedStyleSheets` in `initStyle()`.
   */
  cssStyleSheet = new CSSStyleSheet();
  /**
   * Custom element tag name for this component (once defined).
   */
  tagName;
  /**
   * CSS template tag processor used to transform CSS template literals.
   *
   * Notes
   * -----
   * Defaults to the `css` function imported from './css.ts'. This processor is
   * invoked when compiling class-level styles into the constructable
   * CSSStyleSheet. It may be replaced (for example in tests or subclasses) to
   * provide custom processing such as scoping, variable substitution, or
   * minification prior to writing rules into the stylesheet.
   */
  cssProcessor = css;
  /**
   * Accumulated CSS blocks without selectors.
   *
   * Notes
   * -----
   * - Preserves insertion order (via `addStyle()`).
   * - These snippets are wrapped with the component selector before being
   *   committed to `cssStyleSheet`.
   */
  styles = [];
  /**
   * Concatenated class-level CSS.
   *
   * Returns
   * -------
   * string
   *     The joined stylesheet text for this class only (no superclasses).
   */
  get style() {
    return this.styles.join("\n");
  }
  /**
   * Replace existing class-level CSS and update the stylesheet.
   *
   * Parameters
   * ----------
   * style : string
   *     Entire CSS text to set for this class.
   */
  set style(style) {
    this.styles = [
      style
    ];
    this.updateStyleSheet();
  }
  /**
   * Collect CSS from the inheritance chain.
   *
   * Returns
   * -------
   * string[]
   *     Array of CSS blocks from superclasses followed by this class.
   *
   * Notes
   * -----
   * Superclass styles are added first to preserve expected cascade order.
   */
  get allStyles() {
    let superClass = Object.getPrototypeOf(this.adapterClass);
    const allStyles = [];
    while (superClass.adapter) {
      allStyles.push(...superClass.adapter.styles);
      superClass = Object.getPrototypeOf(superClass);
    }
    allStyles.push(...this.styles);
    return allStyles;
  }
  /**
   * Joined CSS string across the entire inheritance chain.
   *
   * Returns
   * -------
   * string
   *     Combined stylesheet text including superclasses and this class.
   */
  get allStyle() {
    return this.allStyles.join("\n");
  }
  /**
   * Define the custom element and initialize its shared stylesheet.
   *
   * Parameters
   * ----------
   * tagName : string
   *     The custom element tag to register.
   *
   * Raises
   * ------
   * DOMException
   *     If the tag name is invalid or already defined.
   *
   * Examples
   * --------
   * ```ts
   * class Card extends Adapter {}
   * Card.define("el-card");
   * ```
   *
   * Notes
   * -----
   * When extending, call `super.define(tagName)` before subclass-specific work.
   */
  define(tagName) {
    this.tagName = tagName;
    customElements.define(tagName, this.adapterClass);
    this.initStyle();
  }
  /**
   * Attach the shared stylesheet and synchronize its rules.
   *
   * Notes
   * -----
   * Pushes `cssStyleSheet` to `document.adoptedStyleSheets` and compiles the
   * current CSS into it.
   */
  initStyle() {
    document.adoptedStyleSheets.push(this.cssStyleSheet);
    this.updateStyleSheet();
  }
  /**
   * Append a CSS block to this class and update the stylesheet.
   *
   * Parameters
   * ----------
   * style : string
   *     CSS text without a selector (it will be wrapped automatically).
   */
  addStyle(style) {
    this.styles.push(style);
    this.updateStyleSheet();
  }
  /**
   * Compile and replace the constructable stylesheet with current rules.
   *
   * Notes
   * -----
   * No-op until `tagName` is set (i.e., after `define()`).
   */
  updateStyleSheet() {
    if (!this.tagName) {
      return;
    }
    const css2 = this.cssProcessor`${this.tagName} { ${this.allStyle} }`;
    this.cssStyleSheet.replaceSync(css2);
  }
};
var AdapterObjectController = class {
  /**
   * The owning Adapter element instance.
   *
   * Notes
   * -----
   * Set by the Adapter mixin constructor immediately after instantiation.
   */
  adapterObject;
  /**
   * Constructable stylesheet used for instance-scoped CSS rules.
   *
   * Notes
   * -----
   * Registered with the element's root node via adoptedStyleSheets when connected.
   */
  cssStyleSheet = new CSSStyleSheet();
  /**
   * Lazily generated UUID for the element.
   *
   * Notes
   * -----
   * - Used to create a unique class selector on the element.
   * - Stable for the lifetime of this controller once generated.
   */
  _uuid;
  /**
   * MutationObserver for tracking `css` attribute changes on the element.
   *
   * Notes
   * -----
   * Automatically updates `adapterObject.css` when the `css` attribute changes.
   */
  _cssObserver;
  /**
   * Cached Adapter class (constructor) for the owning element.
   *
   * Notes
   * -----
   * Populated in `initClass()` and used to access class-level controller state.
   */
  _class;
  /**
   * Unique identifier for this element used in generated selectors.
   *
   * Returns
   * -------
   * string
   *     The UUID in the form `${tagName}-${random}`.
   *
   * Notes
   * -----
   * Generated on first access and then cached.
   */
  get uuid() {
    if (this._uuid) {
      return this._uuid;
    }
    ;
    this._uuid = `${this.adapterObject.tagName}-${uuid()}`;
    return this._uuid;
  }
  /**
   * A MutationObserver instance that mirrors `css` attribute changes to styles.
   *
   * Returns
   * -------
   * MutationObserver
   *     The observer configured to watch attribute mutations on the element.
   *
   * Notes
   * -----
   * Created lazily and reused for subsequent observations.
   */
  get cssObserver() {
    if (this._cssObserver) {
      return this._cssObserver;
    }
    ;
    this._cssObserver = new MutationObserver((mutations) => {
      for (const mutation of mutations) {
        if (mutation.attributeName === "css") {
          this.adapterObject.css = this.adapterObject.getAttribute("css") || "";
        }
        ;
      }
      ;
    });
    return this._cssObserver;
  }
  /**
   * Selector for this element represented as a dot-joined class chain.
   *
   * Returns
   * -------
   * string
   *     The element's classList joined with '.' (e.g., "a.b.c").
   */
  get objectClassSelector() {
    return this.adapterObject.classList.value.replace(/ /g, ".");
  }
  /**
   * Initialize class-level links and ensure the class stylesheet is ready.
   *
   * Notes
   * -----
   * - Captures the Adapter constructor from the instance.
   * - If the class tagName is not set, initializes it and attaches the shared stylesheet.
   * - No-op if the class tagName is already defined.
   */
  initClass() {
    this._class = this.adapterObject.constructor;
    if (this._class.adapter.tagName) {
      return;
    }
    this._class.adapter.tagName = this.adapterObject.tagName;
    this._class.adapter.initStyle();
  }
  /**
   * Enable or disable observation of the element's `css` attribute.
   *
   * Parameters
   * ----------
   * enable : boolean
   *     True to start observing, false to disconnect.
   *
   * Notes
   * -----
   * Observation is limited to attribute mutations on the host element.
   */
  cssObserve(enable) {
    if (enable) {
      this.cssObserver.observe(this.adapterObject, {
        attributes: true
      });
    } else {
      this.cssObserver.disconnect();
    }
  }
};
function AdapterMixin(Base2) {
  return class _Adapter extends Base2 {
    /** Static instance of AdapterClassController */
    static _adapter;
    /**
     * Get the AdapterClassController instance.
     */
    static get adapter() {
      const parentClass = Object.getPrototypeOf(this);
      if (this._adapter === parentClass._adapter) {
        const parentAdapter = "adapter" in parentClass ? parentClass.adapter : void 0;
        this._adapter = new AdapterClassController();
        this._adapter.adapterClass = this;
        if (parentAdapter) {
          this._adapter.cssProcessor = parentAdapter.cssProcessor;
        }
      }
      return this._adapter;
    }
    /**
     * Create a configured subclass branch without mutating the current class.
     */
    static configure(options = {}) {
      return class ConfiguredAdapter extends this {
        static {
          if (options.cssProcessor) {
            this.adapter.cssProcessor = options.cssProcessor;
          }
        }
      };
    }
    /**
     * Set the CSS for the component.
     */
    static set css(css2) {
      this.adapter.style = css2;
    }
    /**
     * Get the CSS for the component.
     */
    static get css() {
      return this.adapter.style;
    }
    /**
     * Get the tag name of the component.
     */
    static get tagName() {
      return this.adapter.tagName;
    }
    /**
     * Add style to this component.
     */
    static addStyle(css2) {
      this.adapter.addStyle(css2);
    }
    /**
     * Define component to element tag and init component style.
     * To extend this function, sub-elements must be defined
     * before calling this function as `super.define(tagName);`
     */
    static define(tagName) {
      this.adapter.define(tagName);
    }
    /** Instance of AdapterObjectController */
    _adapter = new AdapterObjectController();
    /**
     * Constructor to initialize the AdapterObjectController.
     */
    // deno-lint-ignore no-explicit-any
    constructor(...args) {
      super(...args);
      this._adapter.adapterObject = this;
      if (!this._adapter._class) {
        this._adapter.initClass();
      }
      ;
      this._adapter.cssObserve(true);
    }
    /**
     * Set CSS for this element with tag name.
     */
    set css(css2) {
      this.classList.add(this._adapter.uuid);
      const cssRule = `${this.tagName}.${this._adapter.objectClassSelector} { ${css2} }`;
      this._adapter.cssStyleSheet.replaceSync(this._adapter._class.adapter.cssProcessor`${cssRule}`);
    }
    /**
     * Get CSS for this element.
     */
    get css() {
      let css2 = this.getAttribute("css") || "";
      if (css2) {
        return css2;
      }
      ;
      for (const rule of this._adapter.cssStyleSheet.cssRules) {
        css2 += rule.cssText + "\n";
      }
      return css2;
    }
    /**
     * Add style for this element.
     */
    addStyle(css2) {
      this.classList.add(this._adapter.uuid);
      const cssRule = `${this.tagName}.${this._adapter.objectClassSelector} { ${css2} }`;
      this._adapter.cssStyleSheet.replaceSync(`
        ${this.css}
        ${this._adapter._class.adapter.cssProcessor`${cssRule}`}
      `);
    }
    /**
     * Register CSSStyleSheet() object to `rootNode.adoptedStyleSheets`.
     * This function will check the existing CSSStyleSheet() before applying
     * to make sure that it won't create duplicates.
     */
    _registCSSStyleSheet() {
      const css2 = this.getAttribute("css");
      if (css2) {
        this.css = css2;
      }
      ;
      const rootNode = this.getRootNode();
      if (rootNode.adoptedStyleSheets.indexOf(this._adapter._class.adapter.cssStyleSheet) === -1) {
        rootNode.adoptedStyleSheets.push(this._adapter._class.adapter.cssStyleSheet);
      }
      if (rootNode.adoptedStyleSheets.indexOf(this._adapter.cssStyleSheet) === -1) {
        rootNode.adoptedStyleSheets.push(this._adapter.cssStyleSheet);
      }
    }
    /** Callback when the element is connected to the DOM */
    connectedCallback() {
      super.connectedCallback ? super.connectedCallback() : null;
      this._registCSSStyleSheet();
    }
    /** Remove the element from DOM and remove adoptedStyleSheet */
    remove() {
      const rootNode = this.getRootNode();
      const i = rootNode.adoptedStyleSheets.indexOf(this._adapter.cssStyleSheet);
      rootNode.adoptedStyleSheets.splice(i, 1);
      super.remove();
    }
  };
}
var Adapter = class extends AdapterMixin(HTMLElement) {
  // Redeclare Adapter's static API directly so editor tooling can resolve
  // completions on the exported class without tracing the mixin result.
  static get adapter() {
    return super.adapter;
  }
  static configure(options = {}) {
    return super.configure(options);
  }
  static set css(css2) {
    super.css = css2;
  }
  static get css() {
    return super.css;
  }
  static get tagName() {
    return super.tagName;
  }
  static addStyle(css2) {
    super.addStyle(css2);
  }
  static define(tagName) {
    super.define(tagName);
  }
};

// docs-src/_ui/components/resolved-styles.ts
var componentStyles = define_NW_COMPONENT_STYLES_default;

// docs-src/_ui/components/base.ts
var Base = class extends Adapter {
  static {
    this.css = componentStyles.base;
  }
  /** Register this class once without replacing another component's definition. */
  static define(tagName) {
    const existing = customElements.get(tagName);
    if (existing && existing !== this) throw new Error(`Foreign definition for ${tagName}`);
    if (!existing) super.define(tagName);
  }
};

// docs-src/_ui/components/button.ts
var Button = class extends Base {
  static {
    this.css = componentStyles.button;
  }
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
var Card = class extends Base {
  static {
    this.css = componentStyles.card;
  }
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
  Button.define("nw-button");
  Card.define("nw-card");
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
