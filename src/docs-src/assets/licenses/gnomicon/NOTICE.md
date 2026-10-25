# Gnomicon icon attribution

The `edit-copy` artwork embedded in `_ui/components/gnomicon-copy.ts` is copied
from [Gnomicon 51.0.0](https://keenlycode.github.io/gnomicon/),
[official SVG](https://keenlycode.github.io/gnomicon/lib/gnomicon/svg/edit-copy.svg).
Artwork: [GNOME Project](https://www.gnome.org/), Icon Development Kit,
[CC0 1.0 Universal](https://creativecommons.org/publicdomain/zero/1.0/).
Pinned upstream revision and original path are in `provenance.json`.
Gnomicon contributions by Nitipit Nontasuwan use
[CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/);
see the included original `LICENSE.md` and upstream `COPYING.md`.

Gnomicon's upstream processing includes color normalization, metadata cleanup,
SVG optimization and wrappers. NodalWire preserves the official SVG geometry and
currentColor, stores it in a TypeScript literal, and adds only decorative
`aria-hidden`/`focusable` accessibility attributes when creating a native control.
No package/catalog is installed and no runtime network request is needed.
The copied SVG asset and any changes to that asset retain the applicable upstream
licenses; this notice does not relicense unrelated application code.

## Navigation additions

The floating design menu embeds only official Gnomicon 51.0.0 `open-menu` and
`pan-end` SVGs, copied byte-for-byte into `assets/icons/gnomicon/`. Their filenames,
public source URLs, SHA256 and pinned GNOME source paths are recorded under
`navigationIcons` in `provenance.json`. Both upstream files at revision
`e5857f6d796a96571a61030db40f35bfb8815a94` identify Jakub Steiner as creator and
CC0-1.0 artwork licensing in their RDF metadata. Existing COPYING.md covers that
upstream collection; the existing Gnomicon LICENSE.md contribution terms remain.
The server include adds only decorative `aria-hidden` and `focusable` attributes.
`pan-end` points right; CSS rotates it 90 degrees for expanded/down. No geometry
is redrawn, runtime external asset fetched or icon package installed.
