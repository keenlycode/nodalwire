"""Render URL-shaped Engrave sources, validate local links, publish generated docs/."""

import argparse
import json
import posixpath
import shutil
from html.parser import HTMLParser
from pathlib import Path, PurePosixPath
from urllib.parse import unquote, urlsplit

import jinja2
from engrave.template import get_template


def page_url(page: PurePosixPath, target: str) -> str:
    """A source-root-relative destination becomes a page-relative, Pages-safe URL."""
    if target.startswith("/") or ".." in PurePosixPath(target).parts:
        raise ValueError("Use source-root-relative destinations without a leading slash or '..'")
    relative = posixpath.relpath(target or ".", str(page.parent))
    if not target or target.endswith("/"):
        return relative.rstrip("/") + "/"
    return relative


class Links(HTMLParser):
    def __init__(self):
        super().__init__()
        self.ids: set[str] = set()
        self.references: list[str] = []

    def handle_starttag(self, tag, attrs):
        values = dict(attrs)
        if identifier := values.get("id"):
            if identifier in self.ids:
                raise ValueError(f"Duplicate HTML id: {identifier}")
            self.ids.add(identifier)
        for name in ("href", "src"):
            if value := values.get(name):
                self.references.append(value)

    handle_startendtag = handle_starttag


def validate_links(directory: Path) -> None:
    directory = directory.resolve()
    pages: dict[Path, Links] = {}
    for page in directory.rglob("*.html"):
        parser = Links()
        parser.feed(page.read_text(encoding="utf-8"))
        pages[page.resolve()] = parser
    for page, parser in pages.items():
        for reference in parser.references:
            url = urlsplit(reference)
            if url.scheme or url.netloc:
                continue  # External destinations are not fetched during builds.
            if url.path.startswith("/"):
                raise ValueError(f"Root-relative link breaks a Pages project prefix: {reference}")
            destination = (page.parent / unquote(url.path)).resolve() if url.path else page
            if not destination.is_relative_to(directory):
                raise ValueError(f"Link leaves the generated site: {reference}")
            if destination.is_dir():
                destination /= "index.html"
            if not destination.is_file():
                raise ValueError(f"Broken local link in {page.name}: {reference}")
            if url.fragment and destination in pages:
                if unquote(url.fragment) not in pages[destination].ids:
                    raise ValueError(f"Missing anchor in {destination.name}: {reference}")


# These raw SVGs are embedded only by design templates, despite living under
# the shared icon directory. Keep shared copy-icon attribution/licenses intact.
DEVELOPMENT_ONLY_ASSETS = frozenset({
    "icons/gnomicon/open-menu.svg",
    "icons/gnomicon/pan-end.svg",
})


NAVIGATION = [
    {"label": "", "items": [{"label": "Home", "path": ""},
                              {"label": "Getting Started", "path": "getting-started/"}]},
    {"label": "Guides", "items": [
        {"label": "Networks", "path": "guides/networks/"},
        {"label": "Request/reply", "path": "guides/request-reply/"},
        {"label": "Security", "path": "guides/security/"}]},
    {"label": "Reference", "items": [
        {"label": "Python & Node API", "path": "reference/api/"},
        {"label": "CLI", "path": "reference/cli/"},
        {"label": "Configuration", "path": "reference/config/"},
        {"label": "Administration", "path": "reference/admin/"}]},
]


def render_site(source: Path, stage: Path, data: dict, *, development: bool = False) -> None:
    load = get_template(
        dir_src=source,
        autoescape=jinja2.select_autoescape(["html"]),
        undefined=jinja2.StrictUndefined,
        trim_blocks=True,
        lstrip_blocks=True,
    )
    for page in sorted(source.rglob("*.html")):
        relative = page.relative_to(source)
        if any(part.startswith("_") for part in relative.parts):
            continue
        if not development and relative.parts[0] == "design":
            continue
        destination = stage / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        page_path = PurePosixPath(relative.as_posix())
        rendered = load(relative.as_posix()).render(
            **data, development=development, navigation=NAVIGATION,
            url=lambda target, current=page_path: page_url(current, target)
        )
        destination.write_text(rendered + "\n", encoding="utf-8")
    assets = source / "assets"
    if assets.is_dir():
        for asset in assets.rglob("*"):
            if asset.is_symlink():
                raise ValueError("Static assets may not be symlinks")
            if asset.is_file():
                relative_asset = asset.relative_to(assets)
                if not development and (
                    relative_asset.parts[0] == "design"
                    or relative_asset.as_posix() in DEVELOPMENT_ONLY_ASSETS
                ):
                    continue
                destination = stage / "assets" / asset.relative_to(assets)
                if destination.exists():
                    raise ValueError(f"Static asset collides with a generated file: {destination}")
                destination.parent.mkdir(parents=True, exist_ok=True)
                shutil.copyfile(asset, destination)
    (stage / ".nojekyll").write_text("", encoding="utf-8")
    validate_links(stage)


def publish(stage: Path, source: Path, output: Path) -> None:
    # Own only <root>/docs for maintained inputs at <root>/src/docs-src.
    if (
        source.name != "docs-src"
        or source.parent.name != "src"
        or source.is_symlink()
        or output.name != "docs"
        or output.parent.resolve() != source.parent.parent.resolve()
        or source.resolve() != output.parent.resolve() / "src" / "docs-src"
    ):
        raise ValueError("Output must be <root>/docs/ for source <root>/src/docs-src/")
    if output.is_symlink():
        raise ValueError("Refusing to replace a symlinked docs/ output")
    if output.exists():
        if not (output / ".nojekyll").is_file():
            raise ValueError("Existing docs/ is not marked as generated; refusing to replace it")
        shutil.rmtree(output)
    shutil.copytree(stage, output)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "stage", "output", "data"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--dev", action="store_true", help="Include the local design playground")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    render_site(args.source, args.stage, data, development=args.dev)
    publish(args.stage, args.source, args.output)


if __name__ == "__main__":
    main()
