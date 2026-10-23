# Documentation build

`docs-src/` is the maintained source. `docs/` is generated static output intended
for GitHub Pages' **Deploy from a branch → /docs** option. Do not edit generated
files by hand: rebuilding replaces that directory. Commit source and output
together when a documentation change is ready. Building does not commit, push,
configure Pages, or deploy anything.

## Setup and build

From the repository root, with Node.js 24+, pnpm 12.5.1, Python 3.12+, and uv:

```sh
pnpm --dir tools/docs install --frozen-lockfile
uv sync --project tools/docs --locked
pnpm --dir tools/docs verify
```

After setup, `pnpm --dir tools/docs build` rebuilds the site. A global Engrave
installation is optional; the build uses the exact version in this tooling
project's `uv.lock`. These dependencies do not enter NodalWire's runtime project.
The local pnpm policy explicitly denies esbuild's lifecycle script; the optional
platform-specific binary is used instead. Unreviewed-build protection stays on.

To preview only public output:

```sh
uv run --project tools/docs --locked python -m http.server 8765 \
  --bind 127.0.0.1 --directory docs
```

Open `http://127.0.0.1:8765/design/tokens/`. Stop the server with Ctrl-C.
Do not serve the repository root, tooling directories, or kernel task storage.

## Source ownership

- `docs-src/_ui/tokens/`: canonical TypeScript palette, semantic recipes,
  typography, spacing, radius, layout, and lift. `tokens.lift` preserves Adaptive's
  six palette-derived `drop-shadow` filters (0–5), not box shadows or z-index.
  The original Adaptive/GNOME palette
  remains intact; pink is a labeled NodalWire extension.
- `_layouts/`: shared Engrave/Jinja layout and its colocated CSS-in-JS.
- `_partials/`: reusable template fragments, not standalone pages.
- `design/tokens/`: the review page, colocated `style.ts`, and `index.ts` behavior.
- `tools/docs/`: isolated build dependencies, scripts, locks, and tests.

Public HTML directories directly reflect URL paths. Shared underscore-prefixed
HTML files are not pages. `style.ts` files export a default function receiving
resolved tokens and returning CSS. The build discovers these files and emits
matching paths under `docs/assets/`. Public `index.ts` files are bundled likewise.
No page routing manifest is needed.

## Build pipeline

1. esbuild resolves canonical TypeScript and Color.js in Node.
2. Semantic aliases and explicit OKLCH tint recipes resolve to sRGB colors. Six
   reviewed normal-text contrast pairs must meet WCAG AA (4.5:1); this is not a
   full accessibility audit.
3. CSS-in-JS functions produce CSS; esbuild bundles page behavior independently.
   A graph check rejects Color.js in browser bundles.
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
