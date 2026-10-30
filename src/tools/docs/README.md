# Documentation build

`src/docs-src/` is the maintained source. Root `docs/` is ignored, generated local
preview output, not source-branch content. Do not edit generated files by hand:
rebuilding replaces that directory. Commit maintained source/tooling/tests on the
source branch; publish validated static output separately at the dedicated
`docs` branch root (Pages **Deploy from a branch → docs → /(root)**), only after
release/publication and deployment approval. Building does not commit, push,
configure Pages, or deploy anything. No generated site assets belong in `main`.

## Setup and build

From the repository root, with Node.js 24+, pnpm 12.5.1, Python 3.12+, and uv:

```sh
pnpm --dir src/tools/docs install --frozen-lockfile
uv sync --project src/tools/docs --locked
pnpm --dir src/tools/docs verify
```

After setup, `pnpm --dir src/tools/docs build` rebuilds the **public product site**.
The default excludes `/design/`, its navigation and showcase bundles/styles.
`pnpm --dir src/tools/docs build:dev` explicitly includes the local design playground,
including all six detailed token pages. Both modes use the same templates,
components, tokens and pipeline; each replaces the marked generated `docs/`
directory, so a public rebuild also removes stale development output.
`verify` runs the design-dependent suites against an explicit development build,
then rebuilds public output after successful checks. A failed verification can leave
development output; run `build` before any public handoff. A global Engrave
installation is optional; the build uses the exact version in this tooling
project's `uv.lock`. These dependencies do not enter NodalWire's runtime project.
The local pnpm policy explicitly denies esbuild's lifecycle script; the optional
platform-specific binary is used instead. Unreviewed-build protection stays on.

To preview only public output:

```sh
uv run --project src/tools/docs --locked python -m http.server 8765 \
  --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8765/`. For the explicitly enabled development build,
`http://127.0.0.1:8765/design/` opens the playground. Stop the server with Ctrl-C.
Do not serve the repository root, tooling directories, or kernel task storage.

## Dedicated publishing candidate

Keep the existing `docs` branch history. Fetch/inspect its latest tip, then base a
new candidate on that tip; do not create an orphan replacement or force-push.
The existing remote tip may still contain source files, so a reviewed append-only
conversion commit is required before it can serve only the public site.

Build with `pnpm --dir src/tools/docs build` (not `build:dev`). Copy only its
validated generated public files, including `.nojekyll`, into an isolated site
artifact and the candidate's root. Never copy credentials, task state,
`node_modules`, build tooling or the source checkout. Preserve the candidate's
`.git` link; never point a destructive build-output replacement at a Git worktree
root. Review deletions of the old branch tree and compare every copied byte to
the generated artifact. The normal local `docs/` path remains ignored for existing
development/test commands.

Publication order is a separate approval gate: verify matching Python/Node
artifacts, approve and publish both packages, verify registry availability, then
approve source/tag/docs pushes and Pages configuration/deployment. Do not publish
a public site that promises package versions before those versions exist.
Repository visibility and Git identity privacy are separate gates; a private Free
repository cannot be assumed to have Pages enabled. Prepare locally without
changing remote state while those decisions wait.

## Source ownership

All source-relative paths below are under `src/docs-src/` unless stated otherwise.

- `_ui/tokens/`: canonical TypeScript palette, semantic recipes,
  typography, spacing, radius, layout, and lift. `tokens.lift` preserves Adaptive's
  six palette-derived `drop-shadow` filters (0–5), not box shadows or z-index.
  The original Adaptive/GNOME palette
  remains intact; pink is a labeled NodalWire extension.
- `_layouts/`: shared Engrave/Jinja layout and its colocated CSS-in-JS.
- `_partials/`: reusable template fragments, not standalone pages.
- `_ui/components/`: flat custom-element modules. Button and Card inherit Base,
  which extends the real Adapter 4.0.0 (`@devcapsule/adapter`, resolved from the
  exact JSR revision-11 tarball in the tooling lock). Base adds shared typography,
  text and box-sizing CSS and idempotent `.define(tagName)` registration with
  foreign-definition protection. After defining, Base deduplicates only that
  class's own Adapter stylesheet reference: Adapter can append it twice when
  registration upgrades already-authored SSR hosts. The actual installed Adapter
  still owns inherited class constructable
  stylesheets and isolated instance `.css`/`css`-attribute styling in light DOM.
  Native inner-button attributes/content remain authoritative.
  Build-only `recipes.ts` is the single token-derived styling source: esbuild
  injects resolved strings for Adapter static CSS; `style.ts` emits the same
  recipes as a static no-JS fallback. No Color.js reaches browser bundles.
  Modern CSS nesting and constructable stylesheets are required for enhancement;
  without JS, authored native controls and the static stylesheet remain usable.
- `design/`: landing page linking to Tokens and Components, with the same shared
  menu and a minimal registration/enhancement entry point. Every design page has
  one `main#main` containing `nw-container`, then a semantic `.page-header`, content
  sections and an optional page footer. Container centers a fluid border-box with
  a 1000px outer cap and token-derived responsive side padding; it adds no height,
  surface or content semantics. The floating menu remains outside that wrapper.
  Page headers start with caller-authored `nw-page-path` location links, followed
  by one page title and its introduction. The Tokens overview keeps its former
  section links in ordinary content flow rather than a separate sidebar.
- `design/tokens/`: concise overview with six linked, token-derived Card previews.
  Complete scales, values, recipes and playgrounds live on `color/` (palette and
  semantics together), `typography/`, `spacing/`, `radius/`, `layout/`, and `lift/`.
  The overview has no duplicated full specimens or old in-page section menu.
  All resolve canonical data; shared `style.ts` and specimen-optional `index.ts`
  behavior serve the overview and children.
- `design/components/`: useful combined overview plus focused `button/`,
  `button-pin/`, `card/`, `icon-button/`, `code-block/`, `link/`, `badge/`,
  `inline-code/`, `top-navigation/`, `bottom-navigation/`, and `menu-stack/` pages.
  Server-authored native specimens are shared through private Jinja includes;
  optional factories attach only where their authored specimen containers exist.
- `design/_include/navigation.html`: the single server-rendered Jinja/native-HTML
  hierarchy linking the 19 token/component reference routes with current-page and
  parent context. The design landing page uses the same hierarchy without marking
  either section as current.
  `design/_include/layout.html` composes ONE bottom-left ButtonPin and ONE combined
  MenuStack; reusable TopNavigation/BottomNavigation classes remain available but
  are not instantiated by the design shell. Each single header row pairs a Tokens/Components overview link with a separate
  native summary control. Official Gnomicon `pan-end` chevrons point right when
  collapsed and rotate down when expanded. Parent links never toggle disclosures;
  summaries never navigate. The circular pin embeds the official `open-menu` SVG
  and its accessible name follows open/closed state. Both selected public SVGs
  and per-icon provenance are distributed with the existing Gnomicon licenses.
  `navigation.ts` progressively enhances this composition once per document. The
  native inner button owns `aria-expanded` and `aria-controls`; native `hidden`
  removes closed links from layout/focus, Escape restores button focus, and group
  state survives closing/reopening the whole panel. There is no menu/tree role,
  focus trap or modal keyboard model. Without JS, the inert pin stays hidden and
  all native links/disclosures are reachable in ordinary document flow.
  Design-only CSS supplies fixed bottom-left safe-area clearance and one bounded
  vertical scroll container above the approved 2.75rem circular ButtonPin. A
  rounded, non-scrolling outer shell owns the border/background/lift and clips
  children. A Design heading link to the landing page and a divider remain above
  the scroll area. Its blue-tinted surface fills the shell's rounded top edge;
  token-spaced padding insets the ONE native MenuStack scroller
  from every corner. The inner stack shrinks only at the available viewport
  maximum, contains scroll chaining, and progressively requests a quiet thin
  native scrollbar; no replacement scrollbar or body scroll lock is used.
  Content density is retained by splitting the existing padding across shell
  and scroller. The embedded stack uses `--nw-menu-stack-height:auto`; standalone MenuStack retains
  its viewport-height contract. Canonical palette, spacing, radius and lift tokens
  supply the calm surface, hierarchy, blue active accent and focus treatment.
- `src/tools/docs/` (repository-relative): isolated build dependencies, scripts,
  and locks. All maintained tests live under root `tests/`: module-mirrored
  `tests/unit/docs-src/` and `tests/unit/tools/docs/`, plus cross-component/site
  flows in `tests/integration/docs/`. Shared test helpers live in `tests/helpers/`.

Product pages extend `_layouts/product.html`, setting `page_path`, `page_title`,
`page_intro` and optional `page_ancestors` (linked `{label, path}` entries).
The layout owns the main/Container/page-header/Page Path and single h1; leaf pages
supply only the `content` block. `_partials/code-block.html` exports
`code_block(text, filename='', language='')`, also available through the product
layout. Pass exact text, including a final newline when intended; the macro escapes
HTML and preserves carriage returns through character references. Shared native
navigation is supplied by the renderer, with no fake guide/reference index routes.

Public HTML directories directly reflect URL paths. Shared underscore-prefixed
HTML files are not pages. `style.ts` files export a default function receiving
resolved tokens and returning CSS. The build discovers these files and emits
matching paths under `docs/assets/`. Public `index.ts` files are bundled likewise.
The examples in `tests/integration/docs/examples_test.py` and
`guides_examples_test.py` run in the existing root locked Python environment via
pytest; the docs venv intentionally does not absorb NodalWire/pytest runtime
packages. Renderer/navigation unittest checks remain in the docs environment.

No page routing manifest is needed for rendering. The renderer's small navigation
inventory names the nine public destinations; development-only design pages remain
automatically discovered.

## Build pipeline

1. esbuild resolves canonical TypeScript and Color.js in Node.
2. Semantic aliases and explicit OKLCH tint recipes resolve to sRGB colors. Six
   reviewed normal-text contrast pairs must meet WCAG AA (4.5:1); this is not a
   full accessibility audit.
3. CSS-in-JS functions produce CSS; esbuild emits minified ES modules with shared
   chunks, preserving class names. CodeBlock dynamically imports Shiki core and
   its JavaScript regex engine, then only the requested Python/JavaScript grammar.
   A graph check rejects Color.js in browser bundles. Runtime package licenses
   are collected into `assets/licenses/runtime/NOTICE.txt`.
4. Engrave's `get_template()` API renders Jinja templates with the resolved token
   data and Markdown helpers. Undefined template data is an error. Page-relative
   asset/navigation URLs work both locally and below `/nodalwire/` on Pages.
5. Local links and fragment targets are checked before replacing `docs/`.
   `.nojekyll` tells Pages to serve the generated files directly, including
   underscore-prefixed asset directories.

The Python kernel is optional for iteration, never required for a clean build.
For live review it can run the same build command, then use a local Web Runtime
host to serve the real generated page at its normal URL, such as
`/design/tokens/`, without an iframe. The development server adds the bridge only
to its in-memory HTML response; maintained source and generated files remain
bridge-free. Only generated `docs/` is served, not source, repository roots,
connection files, or task state. Full navigation replaces the browser session:
the development adapter must admit and attach a new session after a rebuild or
navigation. Keep admission credentials private, and avoid blocking the kernel's
HTTP event loop with synchronous browser-control calls. Temporary DOM/CSS
experiments require design approval before writing their changes into source.
Web Runtime remains task-local development tooling, not a site dependency.

Tests exercise token/lift derivation, contrast failures, Engrave rendering,
local-link validation, browser-bundle boundaries, and byte-identical repeated
builds. The lift specimens and their resolved recipes are server-rendered; native
page controls enhance them without duplicating token values in JavaScript.

Root `tests/unit/docs-src/_ui/components/*.test.mjs` adds module-mirrored
real-browser component regression coverage using
Node's built-in WebSocket and an explicitly owned Chrome DevTools WebSocket
endpoint supplied as `DOCS_TEST_CDP` to the verification subprocess. It creates and
closes only its own testing target; it does not launch a browser or install tools.
Use a task-owned isolated browser, never a personal/default profile. Without that
explicit endpoint the browser suite is reported as skipped: ordinary `verify`
still checks TypeScript, builds and the original Node/Python tests, but does **not**
establish browser behavior proof. With an owned endpoint, the suite exercises
real Adapter inheritance, Base styles, shared-sheet registration/reconnection,
instance CSS isolation, safe factories, validation, authored native
attributes/content, Card composition, and native submit/reset/disabled behavior. Actual keyboard, static JS-disabled
rendering and visual review require separate bounded browser checks.

## Component APIs and ownership

All components use the installed Adapter 4.0.0 → Base foundation, light DOM and
flat `_ui/components/` modules. `registerComponents()` safely defines all tags.
`recipes.ts` alone owns token-derived component CSS; both injected Adapter class
styles and the static no-JS stylesheet derive from it. Native children stay
semantically authoritative; hosts do not invent control roles or keyboard models.

| Class / tag | Factory | Native content / behavior |
| --- | --- | --- |
| Container / `nw-container` | Native construction/authored children | Layout only: centered, fluid width capped at 1000px including responsive padding; light-DOM content remains caller-owned. |
| PagePath / `nw-page-path` | Authored native `nav` / `ol` / `li` / `a` | Linked location segments; caller supplies destinations and marks the current segment with `aria-current="page"`. Official decorative chevrons are supplied by the design template, not generated by the component. |
| Button / `nw-button` | `create({label, type?, disabled?})` | One direct `<button>`; `.button` returns it. |
| ButtonPin / `nw-button-pin` | Same Button options | Circular 2.75rem native button; inherits Button behavior. Shape only, with no fixed positioning or menu binding. |
| IconButton / `nw-icon-button` | Same Button options | Explicit nonempty label becomes native `aria-label`; decorative official Gnomicon copy SVG. |
| Card / `nw-card` | `create({children?})` | Preserves supplied nodes and literal strings. |
| CodeBlock / `nw-code-block` | `create({text, filename?, language?})` | Authored `<pre><code>` is canonical; exact whitespace/literal text and internal scrolling. Optional `filename`/`language` attributes populate a top header with the copy button on the right. Runtime Shiki adds safe token spans for Python/JavaScript; copy reads only code text. Persistent polite success/failure feedback. |
| Link / `nw-link` | `create({label, href})` | One direct `<a>`; `.anchor` returns it. Native href/focus/navigation; factory permits HTTP(S), mailto, tel and relative/fragment URLs, rejects executable/data schemes. |
| Badge / `nw-badge` | `create({text})` | Static nonempty text label; no role/tabindex/live-region behavior. |
| InlineCode / `nw-inline-code` | `create({text})` | Native `<code>`, literal whitespace and wrapping; empty text is valid. |
| MenuStack / `nw-menu-stack` | Authored native nav and optional `<details open><summary>` groups | Standalone 100vh fallback / 100dvh height and internal vertical scrolling. Native `hidden` actually hides the host; remove it to show. Destinations, disclosure content and initial state are caller-owned. Set `--nw-menu-stack-height:auto` for ordinary-flow embedding; the design composition additionally lets its caller own overflow. |
| TopNavigation / `nw-top-navigation` | Authored native nav | Normal document flow; no essential content generated by JS. |
| BottomNavigation / `nw-bottom-navigation` | Authored `<details><summary>` + panel | Fixed bottom; full SSR menu opens upward with viewport-bounded internal scrolling. Summary `aria-controls` points to the authored unique panel ID. |

CodeBlock accepts `python`/`py` and `javascript`/`js`. Missing or unsupported
languages and highlighter download/tokenization failures retain plain code. One
shared engine and in-flight grammar cache serve all blocks. The custom syntax
colors derive from the canonical palette and meet normal-text AA contrast on the
code surface. No preset themes, other grammars or Oniguruma WASM are shipped.
Language/filename attribute changes update automatically; after changing code
text directly, call and optionally await `block.highlight()`. Tokenization never
uses `innerHTML`; original separators, Unicode and final newlines are preserved.
For no-JS metadata, author a `.code-block-header > .code-block-labels` containing
`.code-block-filename` and/or `.code-block-language`, as in the CodeBlock specimen.
The component reuses that header; only the copy control requires JavaScript.
`tests/unit/docs-src/_ui/components/code-highlight.test.mjs` checks token offsets
and contrast; `tests/integration/docs/highlight.test.mjs` checks lazy build boundaries and,
with the owned browser, real production imports, no-JS and blocked-download
fallback, exact copying (stub only) and responsive header geometry.

Factories use safe text insertion; authored SSR must escape code/text normally.
Labels for Button/IconButton/Link and Badge text must be nonempty. Native
attributes/content can be authored directly without factories. CodeBlock copy
requires a secure context and Clipboard API permission; unsupported/denied writes
produce truthful accessible failure, never false success. Automation must not
read or overwrite the OS clipboard: the CodeBlock unit suite injects a clipboard stub
only into an owned test target. Real OS permission/manual integration is not
established by those tests. Icon provenance and upstream licenses are distributed
under `assets/licenses/gnomicon/`; only the required official copy/menu/chevron SVGs are embedded,
with currentColor, no runtime fetch or icon-package dependency.

CodeBlock unit tests and `tests/integration/docs/navigation.test.mjs` additionally require
`DOCS_TEST_ORIGIN`, an already-owned
loopback HTTP origin serving generated public docs (for example
`http://127.0.0.1:8765`). Supply it and `DOCS_TEST_CDP` only to the verification
subprocess. Neither value needs private admission fragments, connection keys or
personal browser profiles. Test targets are closed in `finally`; the review target
is not used for clipboard tests. Missing required browser environment values are
reported as skips, not browser verification. Module-mirrored `link.test.mjs`,
`badge.test.mjs`, and `inline-code.test.mjs` unit suites exercise their factories,
native semantics and actual Adapter CSS behavior;
`tests/integration/docs/navigation_test.py` inventories canonical public design routes and checks
single SSR menu, current page, valid design-only destinations and private-include
exclusion. `tests/integration/docs/navigation.test.mjs` covers actual Adapter registration/reconnect,
keyboard focus/disclosure, group retention, Escape return, short-viewport floating layout and native JS-disabled navigation
on the overviews and representative color, ButtonPin and MenuStack child pages.
SSR inventory checks cover all 20 actual design routes, including the main /
Container / page-header structure, PagePath ancestor URLs and current segment,
landing page and `/nodalwire/` link
resolution, open groups and current-parent context. `tests/integration/docs/menu-stack.test.mjs`
checks actual Adapter ancestry/shared and instance styles/reconnect, native
collapse/reopen, whole-host hidden/show and standalone/auto-height sizing.
`tests/unit/docs-src/_ui/components/link.test.mjs` also checks native Link
Tab/Enter activation with a test-local prevented navigation. Node test files run
serially because keyboard suites share the explicitly owned browser; parallel
front/focus changes would invalidate evidence. Container tests cover its actual
Adapter ancestry, caller-owned light DOM, centered 1000px cap and narrow viewport
padding. PagePath tests check native ancestor-link activation with and without
scripts, plus decorative-icon and focus behavior, not maintained title wording.
Missing optional environment values
remain explicit skips; a passing non-browser run is not a browser pass. Visual
review and real OS clipboard permission integration are not replaced by tests.
