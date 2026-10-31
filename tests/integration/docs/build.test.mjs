import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile, readdir, mkdtemp, writeFile, rm } from "node:fs/promises";
import path from "node:path";
import { root, toolRoot, site } from "../../helpers/docs.mjs";
import { api } from "../../helpers/docs-token-api.mjs";
import { buildSite } from "../../../src/tools/docs/build.mjs";

async function snapshot(directory) {
  const result = {};
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const filename = path.join(directory, item.name);
    if (item.isDirectory()) {
      for (const [name, value] of Object.entries(await snapshot(filename))) result[`${item.name}/${name}`] = value;
    } else result[item.name] = (await readFile(filename)).toString("base64");
  }
  return result;
}

test("targeted version builds reproduce files and preserve all non-target output", async () => {
  const directory = site;
  const sentinel = await mkdtemp(path.join(root, "docs/.preservation-fixture-"));
  await writeFile(path.join(sentinel, "preservation-fixture.txt"), "Preserve this fixture byte-for-byte\r\n");
  const otherVersion = await snapshot(sentinel);
  const rootEntries = Object.fromEntries(Object.entries(await snapshot(path.join(root, "docs"))).filter(([name]) => !name.startsWith("dev/") && !["index.html", "versions.json", ".nojekyll"].includes(name)));
  try {
  await buildSite();
  const first = await snapshot(directory);
  await buildSite();
  assert.deepEqual(first, await snapshot(directory));
  assert.ok(".nojekyll" in first);
  assert.ok("index.html" in first);
  for (const route of ["", "getting-started/", "messaging/", "connect-your-apps/", "run-a-relay/", "reference/api/", "protocol/"]) {
    assert.ok(`${route}index.html` in first, `versioned route ${route}`);
  }
  assert.equal(first["specs/nwm3.md"], (await readFile(path.join(root, "src/docs-src/specs/nwm3.md"))).toString("base64"));
  const manifest = JSON.parse(await readFile(path.join(root, "docs/versions.json"), "utf8"));
  assert.equal(manifest.versions.find(v => v.id === "dev").status, "development");
  assert.match(await readFile(path.join(root, "docs/index.html"), "utf8"), /url=dev\//);
  assert.ok(Object.keys(first).every(name => !name.startsWith("design/") && !name.startsWith("assets/design/")));
  for (const icon of ["open-menu", "pan-end"]) {
    assert.ok(!(`assets/icons/gnomicon/${icon}.svg` in first), "raw design-only icons must not leak from shared paths");
  }
  for (const notice of ["LICENSE.md", "NOTICE.md", "COPYING.md", "provenance.json"]) {
    assert.ok(`assets/licenses/gnomicon/${notice}` in first, "shared copy/icon attribution remains distributed");
  }
  for (const [name, value] of Object.entries(first).filter(([name]) => name.endsWith(".html"))) {
    const html = Buffer.from(value, "base64").toString();
    assert.doesNotMatch(html, /(?:href|src)="[^"]*design\//, name);
  }
  const publicMeta = JSON.parse(await readFile(path.join(toolRoot, ".build/browser-metafile.json"), "utf8"));
  assert.ok(Object.keys(publicMeta.inputs).every(name => !name.includes("src/docs-src/design/")));
  await buildSite({ dev: true });
  const dev = await snapshot(directory);
  assert.ok("design/tokens/index.html" in dev);
  for (const icon of ["open-menu", "pan-end"]) {
    assert.ok(`assets/icons/gnomicon/${icon}.svg` in dev, "development keeps original navigation icons");
  }
  for (const token of ["color", "typography", "spacing", "radius", "layout", "lift"]) {
    assert.ok(`design/tokens/${token}/index.html` in dev);
  }
  await buildSite({ dev: true });
  assert.deepEqual(dev, await snapshot(directory));
  await buildSite();
  assert.deepEqual(first, await snapshot(directory), "public rebuild removes all stale dev pages/assets");
  assert.ok(Object.keys(first).every((name) => !/\.(ts|mjs|py|map)$/.test(name)));
  assert.deepEqual(JSON.parse(await readFile(path.join(site, "assets/tokens.json"), "utf8")), api.tokens);
  const meta = JSON.parse(await readFile(path.join(toolRoot, ".build/browser-metafile.json"), "utf8"));
  assert.ok(Object.keys(meta.inputs).length > 0);
  assert.ok(Object.keys(meta.inputs).every((name) => !name.includes("colorjs.io")));
  // Historical design/browser suites run serially after this test; explicit dev fixture.
  await buildSite({ includeDesign: true });
  assert.deepEqual(otherVersion, await snapshot(sentinel));
  const after = await snapshot(path.join(root, "docs"));
  for (const [name, bytes] of Object.entries(rootEntries)) assert.equal(after[name], bytes, `preserved ${name}`);
  } finally {
    await rm(sentinel, { recursive: true, force: true });
  }
});
