"""Render URL-shaped Engrave sources, validate local links, publish generated docs/."""

import argparse
import json
import posixpath
import re
import shutil
import tempfile
from html import escape
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
    {"label": "Overview", "path": ""},
    {"label": "Get started", "path": "getting-started/"},
    {"label": "Messaging", "path": "messaging/"},
    {"label": "Connect your apps", "path": "connect-your-apps/"},
    {"label": "Run a relay", "path": "run-a-relay/"},
    {"label": "API reference", "path": "reference/api/"},
    {"label": "Protocol & schemas", "path": "protocol/"},
]

DEVELOPMENT_VERSION = {
    "id": "dev", "label": "Development (NWM3 candidate)",
    "path": "dev/", "status": "development",
}


def version_id(value: str) -> str:
    if value != "dev" and not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value):
        raise ValueError("Version must be dev or a strict major.minor.patch identifier")
    return value


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
            docs_version=DEVELOPMENT_VERSION,
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
    # Freeze and expose the maintained wire specification, never a rewritten copy.
    specification = source / "specs" / "nwm3.md"
    if specification.is_file():
        if specification.is_symlink():
            raise ValueError("Protocol specification may not be a symlink")
        (stage / "specs").mkdir(exist_ok=True)
        shutil.copyfile(specification, stage / "specs" / "nwm3.md")
    (stage / ".nojekyll").write_text("", encoding="utf-8")
    validate_links(stage)


def redirect_page(target: str, label: str) -> str:
    # Relative destinations survive both local serving and GitHub project prefixes.
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width, initial-scale=1">'
            f'<meta http-equiv="refresh" content="0; url={escape(target, quote=True)}">'
            '<title>NodalWire documentation</title></head><body><main>'
            f'<h1>NodalWire documentation</h1><p><a href="{escape(target, quote=True)}">'
            f'{escape(label)}</a></p></main></body></html>\n')


def no_symlink(path: Path) -> None:
    if any(parent.is_symlink() for parent in [path, *path.parents]):
        raise ValueError(f"Symlinked publication paths are not allowed: {path}")


def publish(stage: Path, source: Path, output: Path, *, version: str = "dev",
            mode: str = "local", stable_version: str | None = None) -> None:
    version_id(version)
    # This source tree describes an unreleased candidate, not a historical release.
    if version != "dev":
        raise ValueError("Current source may only be published as dev; release import is deferred")
    if mode not in {"local", "artifact"}:
        raise ValueError("Publication mode must be local or artifact")
    if (source.name != "docs-src" or source.parent.name != "src"
            or output.name != "docs"
            or source.resolve() != output.parent.resolve() / "src" / "docs-src"):
        raise ValueError("Output must be <root>/docs/ for source <root>/src/docs-src/")
    for item in (source, output, output / version, output / "index.html",
                 output / ".nojekyll", output / "versions.json"):
        no_symlink(item)
    if output.exists() and not (output / ".nojekyll").is_file():
        raise ValueError("Existing docs/ is not marked as generated; refusing to replace it")
    if not stage.is_dir() or not (stage / "index.html").is_file():
        raise ValueError("Publication stage must contain index.html")
    if any(item.is_symlink() for item in stage.rglob("*")):
        raise ValueError("Publication stage may not contain symlinks")
    validate_links(stage)
    manifest_path = output / "versions.json"
    manifest = json.loads(manifest_path.read_text()) if manifest_path.exists() else {
        "schemaVersion": 1, "latestStable": None, "versions": [],
    }
    if manifest.get("schemaVersion") != 1 or not isinstance(manifest.get("versions"), list):
        raise ValueError("Unsupported documentation version manifest")
    seen = set()
    for entry in manifest["versions"]:
        identifier = version_id(entry["id"])
        if identifier in seen or entry.get("path") != identifier + "/":
            raise ValueError("Invalid or duplicate version entry")
        seen.add(identifier)
    root_target, root_label = "dev/", DEVELOPMENT_VERSION["label"]
    if mode == "artifact":
        # A tag or version string is not evidence of package/source availability.
        if stable_version is None or version_id(stable_version) == "dev":
            raise ValueError("Artifact root requires an explicitly verified existing stable snapshot")
        stable = next((e for e in manifest["versions"] if e["id"] == stable_version), None)
        if not stable or stable.get("status") != "stable" or stable.get("releaseAvailable") is not True:
            raise ValueError("Stable snapshot metadata must explicitly verify release availability")
        stable_root = output / stable_version
        no_symlink(stable_root)
        no_symlink(stable_root / "index.html")
        if not (stable_root / "index.html").is_file():
            raise ValueError("Verified stable snapshot is missing")
        root_target, root_label = stable_version + "/", stable.get("label", stable_version)
        manifest["latestStable"] = stable_version
    elif manifest.get("latestStable") is not None:
        # Preserve a previously verified stable selection, but reject corrupt claims.
        selected = next((e for e in manifest["versions"] if e["id"] == manifest["latestStable"]), None)
        if not selected or selected.get("status") != "stable" or selected.get("releaseAvailable") is not True:
            raise ValueError("Manifest latestStable is not verified")
    manifest["versions"] = sorted(
        [e for e in manifest["versions"] if e["id"] != version] + [DEVELOPMENT_VERSION.copy()],
        key=lambda entry: entry["id"],
    )
    # Preserve the legacy root entry once, outside the served artifact. Never erase
    # the pre-versioning snapshot or any non-target version/root assets.
    backup = source.parent.parent / "src" / "tools" / "docs" / ".build" / "root-index.once.html"
    no_symlink(backup)
    if (output / "index.html").exists() and not backup.exists():
        backup.parent.mkdir(parents=True, exist_ok=True)
        with backup.open("xb") as saved:
            saved.write((output / "index.html").read_bytes())
    output.mkdir(parents=True, exist_ok=True)
    target = output / version
    with tempfile.TemporaryDirectory(prefix=".publish-", dir=output) as temporary:
        incoming = Path(temporary) / "incoming"
        previous = Path(temporary) / "previous"
        shutil.copytree(stage, incoming)
        if target.exists():
            target.rename(previous)
        try:
            incoming.rename(target)
        except BaseException:
            if previous.exists():
                previous.rename(target)
            raise
    (output / ".nojekyll").write_text("", encoding="utf-8")
    manifest_path.write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    (output / "index.html").write_text(redirect_page(root_target, root_label), encoding="utf-8")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ("source", "stage", "output", "data"):
        parser.add_argument(f"--{name}", required=True, type=Path)
    parser.add_argument("--include-design", "--dev", dest="include_design", action="store_true",
                        help="Include the design playground (not a version selector)")
    parser.add_argument("--version", default="dev")
    parser.add_argument("--mode", choices=("local", "artifact"), default="local")
    parser.add_argument("--stable-version")
    args = parser.parse_args()
    data = json.loads(args.data.read_text(encoding="utf-8"))
    render_site(args.source, args.stage, data, development=args.include_design)
    publish(args.stage, args.source, args.output, version=args.version, mode=args.mode,
            stable_version=args.stable_version)


if __name__ == "__main__":
    main()
