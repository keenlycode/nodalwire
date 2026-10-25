// <define:__NW_COMPONENT_STYLES__>
var define_NW_COMPONENT_STYLES_default = { base: "box-sizing:border-box; font-family:system-ui, sans-serif; line-height:1.5; color:#241f31;", button: "display:inline-flex; vertical-align:middle; max-width:100%;\n      & > button { box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; min-height:2.25rem; max-width:100%; margin:0; border:1px solid #1a5fb4; border-radius:0.75rem; padding:0.5rem 1rem; background:#1a5fb4; color:#ffffff; font:inherit; font-size:.875rem; font-weight:500; line-height:1.25; text-align:center; overflow-wrap:anywhere; cursor:pointer; }\n      & > button:hover:not(:disabled) { background:#241f31; border-color:#241f31; }\n      & > button:focus-visible { outline:2px solid #1a5fb4; outline-offset:3px; }\n      & > button:disabled { background:#deddda; border-color:#c0bfbc; color:#5e5c64; cursor:not-allowed; }", buttonPin: "& > button { width:2.75rem; height:2.75rem; min-height:2.75rem; padding:0; border-radius:50%; font-size:.75rem; }", iconButton: "& > button { width:2.25rem; height:2.25rem; padding:0.5rem; flex-shrink:0; } & > button > svg { display:block; width:1rem; height:1rem; }", codeBlock: "display:grid; grid-template-columns:1fr auto; gap:0.5rem; min-width:0; padding:1rem; border:1px solid #c0bfbc; border-radius:0.75rem; background:#f6f5f4;\n      & > pre { grid-column:1 / -1; margin:0; min-width:0; max-width:100%; overflow:auto; padding:0.5rem; font-size:.875rem; line-height:1.6; tab-size:2; }\n      & > pre > code { font-family:ui-monospace,monospace; white-space:pre; }\n      & > nw-icon-button { grid-column:2; grid-row:2; }\n      & > output { grid-column:1; grid-row:2; align-self:center; font-size:.875rem; overflow-wrap:anywhere; }", topNavigation: "display:block; position:static; background:#ffffff; border-bottom:1px solid #c0bfbc; padding:1.5rem;\n      & > .navigation-inner { max-width:80rem; margin:auto; }\n      & .navigation-brand { display:block; font-weight:700; margin-bottom:1rem; }\n      & nav { position:static; margin:0; display:block; }\n      & ul { display:flex; flex-wrap:wrap; gap:0.5rem; list-style:none; padding:0; margin:0; }\n      & a { display:block; padding:0.5rem 1rem; border:0; border-radius:0.25rem; color:#241f31; text-decoration:none; }\n      & a:hover, & a[aria-current=page] { background:#f6f5f4; color:#1a5fb4; }\n      & a:focus-visible { outline:2px solid #1a5fb4; outline-offset:2px; }", bottomNavigation: "display:block; position:fixed; inset:auto 0 0; z-index:5; background:#ffffff; border-top:1px solid #c0bfbc; padding-bottom:env(safe-area-inset-bottom,0px);\n      & > details > summary { box-sizing:border-box; min-height:3.5rem; padding:1rem 1.5rem; cursor:pointer; color:#241f31; font-weight:500; }\n      & > details > summary:focus-visible { outline:2px solid #1a5fb4; outline-offset:-4px; }\n      & > details > .navigation-panel { position:absolute; bottom:100%; left:0; right:0; max-height:calc(100vh - 6rem - env(safe-area-inset-bottom,0px)); max-height:calc(100dvh - 6rem - env(safe-area-inset-bottom,0px)); overflow:auto; overscroll-behavior:contain; background:#ffffff; border-top:1px solid #c0bfbc; padding:1rem 1.5rem; }\n      & nav { position:static; margin:0; display:block; }\n      & ul { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr)); gap:0.5rem; max-width:80rem; margin:0 auto; padding:0; list-style:none; }\n      & a { display:block; padding:1rem; border:0; border-radius:0.25rem; color:#241f31; text-decoration:none; }\n      & a:hover, & a[aria-current=page] { background:#f6f5f4; color:#1a5fb4; }\n      & a:focus-visible { outline:2px solid #1a5fb4; outline-offset:-2px; }", pagePath: "display:block;\n      & nav { position:static; top:auto; display:block; margin:0; }\n      & ol { display:flex; flex-wrap:wrap; align-items:center; gap:0.5rem; list-style:none; margin:0; padding:0; }\n      & li { display:flex; align-items:center; gap:0.5rem; min-width:0; max-width:100%; }\n      & a { display:inline-block; max-width:100%; padding:0.25rem 0; border:0; border-radius:0.25rem; color:#5e5c64; font-size:.8125rem; text-decoration:none; overflow-wrap:anywhere; }\n      & a:hover { color:#1a5fb4; background:transparent; text-decoration:underline; text-underline-offset:.2em; }\n      & a[aria-current=page] { color:#241f31; font-weight:600; }\n      & a:focus-visible { outline:2px solid #1a5fb4; outline-offset:2px; }\n      & li > svg { width:.75rem; height:.75rem; flex:none; color:#5e5c64; }", container: "display:block; box-sizing:border-box; width:100%; max-width:1000px; min-width:0; margin-inline:auto; padding-inline:clamp(1rem, 3vw, 2rem);", menuStack: 'display:block; height:var(--nw-menu-stack-height,100vh); height:var(--nw-menu-stack-height,100dvh); min-width:0; max-width:100%; overflow-y:auto; overflow-x:hidden; overscroll-behavior:contain; background:#ffffff;\n      &[hidden] { display:none !important; }\n      & nav { position:static; display:block; margin:0; }\n      & ul { display:block; list-style:none; margin:0; padding:0; }\n      & li { min-width:0; }\n      & li li { padding-inline-start:1rem; }\n      & a { display:block; padding:0.5rem 1rem; border-radius:0.25rem; color:#241f31; text-decoration:none; overflow-wrap:anywhere; }\n      & a:hover, & a[aria-current=page] { background:#f6f5f4; color:#1a5fb4; }\n      & [data-current-parent] > a { font-weight:700; }\n      & summary { display:flex; align-items:center; justify-content:space-between; gap:1rem; padding:0.5rem 1rem; cursor:pointer; font-weight:500; list-style:none; }\n      & summary::-webkit-details-marker { display:none; }\n      & summary::marker { content:""; }\n      & .menu-stack-toggle { flex:0 0 auto; font-weight:700; }\n      & .when-open { display:none; }\n      & .when-closed { display:inline; }\n      & details[open] > summary .when-open { display:inline; }\n      & details[open] > summary .when-closed { display:none; }\n      & a:focus-visible, & summary:focus-visible { outline:2px solid #1a5fb4; outline-offset:-2px; }', link: "display:inline; & > a { color:#1a5fb4; text-decoration:underline; text-underline-offset:.2em; overflow-wrap:anywhere; } & > a:hover { color:#241f31; } & > a:focus-visible { outline:2px solid #1a5fb4; outline-offset:3px; }", badge: "display:inline-flex; align-items:center; max-width:100%; padding:.125em .5em; border:1px solid #c0bfbc; border-radius:0.25rem; background:#deddda; color:#241f31; font-size:.8125rem; font-weight:500; line-height:1.5; vertical-align:baseline; overflow-wrap:anywhere;", inlineCode: "display:inline; & > code { padding:.125em .375em; border:1px solid #c0bfbc; border-radius:0.25rem; background:#f6f5f4; color:#241f31; font-family:ui-monospace, SFMono-Regular, Consolas, monospace; font-size:.875em; white-space:break-spaces; overflow-wrap:anywhere; box-decoration-break:clone; -webkit-box-decoration-break:clone; }", card: "display:grid; gap:1rem; padding:1.5rem; border:1px solid #c0bfbc; border-radius:0.75rem; background:#ffffff; color:#241f31; min-width:0; overflow-wrap:anywhere;\n      & > :first-child { margin-top:0; } & > :last-child { margin-bottom:0; }" };

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
    if (!existing) {
      super.define(tagName);
      const sheet = this.adapter.cssStyleSheet;
      document.adoptedStyleSheets = document.adoptedStyleSheets.filter(
        (item, index, sheets) => item !== sheet || sheets.indexOf(item) === index
      );
    }
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

// docs-src/_ui/components/button-pin.ts
var ButtonPin = class extends Button {
  static {
    this.css = componentStyles.buttonPin;
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

// docs-src/_ui/components/container.ts
var Container = class extends Base {
  static {
    this.css = componentStyles.container;
  }
};

// docs-src/_ui/components/page-path.ts
var PagePath = class extends Base {
  static {
    this.css = componentStyles.pagePath;
  }
};

// docs-src/_ui/components/gnomicon-copy.ts
var copySVG = '<svg width="16" height="16" fill="currentColor" viewBox="0 0 16 16" xmlns="http://www.w3.org/2000/svg"><path d="m3 10c-1.1046 0-2-0.89543-2-2v-5c0-1.1046 0.89543-2 2-2h5c1.1046 0 2 0.89543 2 2m-4 5v5c0 1.1046 0.89543 2 2 2h5c1.1046 0 2-0.89543 2-2v-5c0-1.1046-0.89543-2-2-2h-5c-1.1046 0-2 0.89543-2 2z" fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="2"/></svg>';

// docs-src/_ui/components/icon-button.ts
var IconButton = class extends Button {
  static {
    this.css = componentStyles.iconButton;
  }
  static create(options) {
    const host = super.create(options);
    host.button.setAttribute("aria-label", options.label);
    host.button.replaceChildren(copyIcon());
    return host;
  }
};
function copyIcon() {
  const parsed = new DOMParser().parseFromString(copySVG, "image/svg+xml");
  const svg = document.importNode(parsed.documentElement, true);
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  return svg;
}

// docs-src/_ui/components/code-block.ts
var CodeBlock = class extends Base {
  static {
    this.css = componentStyles.codeBlock;
  }
  #action;
  #status;
  #pending = false;
  get code() {
    const code = this.querySelectorAll(":scope > pre > code");
    if (code.length !== 1) throw new TypeError("CodeBlock requires exactly one pre/code");
    return code[0];
  }
  static create(options) {
    if (!options || typeof options.text !== "string") throw new TypeError("Code text must be a string");
    const host = new this();
    const pre = document.createElement("pre");
    pre.tabIndex = 0;
    pre.setAttribute("aria-label", "Code example");
    const code = document.createElement("code");
    code.textContent = options.text;
    pre.append(code);
    host.append(pre);
    return host;
  }
  connectedCallback() {
    super.connectedCallback();
    this.code;
    if (this.#action) return;
    const action = this.#action = IconButton.create({ label: "Copy code" });
    const status = this.#status = document.createElement("output");
    status.setAttribute("role", "status");
    status.setAttribute("aria-live", "polite");
    status.textContent = "Ready to copy.";
    action.button.addEventListener("click", () => {
      void this.copy();
    });
    this.append(action, status);
  }
  async copy() {
    if (this.#pending) return;
    this.#pending = true;
    this.#status.textContent = "Copying\u2026";
    const text = this.code.textContent ?? "";
    try {
      if (!window.isSecureContext || !navigator.clipboard?.writeText) throw new Error("Clipboard unavailable");
      await navigator.clipboard.writeText(text);
      this.#status.textContent = "Code copied.";
    } catch {
      this.#status.textContent = "Could not copy. Select and copy the code manually.";
    } finally {
      this.#pending = false;
    }
  }
};

// docs-src/_ui/components/top-navigation.ts
var TopNavigation = class extends Base {
  static {
    this.css = componentStyles.topNavigation;
  }
};

// docs-src/_ui/components/bottom-navigation.ts
var BottomNavigation = class extends Base {
  static {
    this.css = componentStyles.bottomNavigation;
  }
  #bound = false;
  connectedCallback() {
    super.connectedCallback();
    if (this.#bound) return;
    const details = this.querySelector(":scope > details");
    const summary = details?.querySelector(":scope > summary");
    if (!details || !summary) throw new TypeError("BottomNavigation requires native details/summary");
    const sync = () => summary.setAttribute("aria-expanded", String(details.open));
    sync();
    details.addEventListener("toggle", sync);
    new MutationObserver(sync).observe(details, { attributes: true, attributeFilter: ["open"] });
    this.addEventListener("keydown", (event) => {
      if (event.key !== "Escape" || !details.open) return;
      event.preventDefault();
      details.open = false;
      sync();
      summary.focus();
    });
    this.#bound = true;
  }
};

// docs-src/_ui/components/link.ts
var Link = class extends Base {
  static {
    this.css = componentStyles.link;
  }
  get anchor() {
    const anchors = this.querySelectorAll(":scope > a");
    if (anchors.length !== 1) throw new TypeError("Link requires exactly one direct native anchor");
    return anchors[0];
  }
  static create(options) {
    if (!options || typeof options.label !== "string" || !options.label.trim()) throw new TypeError("Link label must be nonempty text");
    if (typeof options.href !== "string" || !options.href.trim()) throw new TypeError("Link href must be nonempty text");
    const url = new URL(options.href, document.baseURI);
    if (!["http:", "https:", "mailto:", "tel:"].includes(url.protocol)) throw new TypeError("Unsupported link protocol");
    const host = new this();
    const anchor = document.createElement("a");
    anchor.setAttribute("href", options.href);
    anchor.textContent = options.label;
    host.append(anchor);
    return host;
  }
};

// docs-src/_ui/components/badge.ts
var Badge = class extends Base {
  static {
    this.css = componentStyles.badge;
  }
  static create(options) {
    if (!options || typeof options.text !== "string" || !options.text.trim()) throw new TypeError("Badge text must be nonempty text");
    const host = new this();
    const span = document.createElement("span");
    span.textContent = options.text;
    host.append(span);
    return host;
  }
};

// docs-src/_ui/components/inline-code.ts
var InlineCode = class extends Base {
  static {
    this.css = componentStyles.inlineCode;
  }
  static create(options) {
    if (!options || typeof options.text !== "string") throw new TypeError("Inline code text must be a string");
    const host = new this();
    const code = document.createElement("code");
    code.textContent = options.text;
    host.append(code);
    return host;
  }
};

// docs-src/_ui/components/menu-stack.ts
var MenuStack = class extends Base {
  static {
    this.css = componentStyles.menuStack;
  }
};

// docs-src/_ui/components/index.ts
function registerComponents() {
  Button.define("nw-button");
  ButtonPin.define("nw-button-pin");
  Card.define("nw-card");
  Container.define("nw-container");
  PagePath.define("nw-page-path");
  IconButton.define("nw-icon-button");
  CodeBlock.define("nw-code-block");
  TopNavigation.define("nw-top-navigation");
  BottomNavigation.define("nw-bottom-navigation");
  Link.define("nw-link");
  Badge.define("nw-badge");
  InlineCode.define("nw-inline-code");
  MenuStack.define("nw-menu-stack");
}

// docs-src/design/_include/navigation.ts
function enhanceDesignNavigation() {
  const host = document.querySelector("[data-design-navigation]");
  if (!host || host.dataset.enhanced) return;
  const pin = host.querySelector("nw-button-pin");
  const button = pin?.querySelector("button");
  const panel = host.querySelector("#design-menu-panel");
  if (!pin || !button || !panel) return;
  host.dataset.enhanced = "true";
  panel.hidden = true;
  pin.hidden = false;
  button.addEventListener("click", () => {
    panel.hidden = !panel.hidden;
    button.setAttribute("aria-expanded", String(!panel.hidden));
    button.setAttribute("aria-label", panel.hidden ? "Open design navigation" : "Close design navigation");
  });
  host.addEventListener("keydown", (event) => {
    if (event.key !== "Escape" || panel.hidden) return;
    event.preventDefault();
    panel.hidden = true;
    button.setAttribute("aria-expanded", "false");
    button.setAttribute("aria-label", "Open design navigation");
    button.focus();
  });
}

// docs-src/design/index.ts
registerComponents();
enhanceDesignNavigation();
