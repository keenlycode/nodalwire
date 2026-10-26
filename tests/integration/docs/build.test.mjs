import assert from "node:assert/strict";
import { test } from "node:test";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { root, toolRoot } from "../../helpers/docs.mjs";
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

test("public and dev builds reproduce all files and public replaces stale design output", async () => {
  const directory = path.join(root, "docs");
  await buildSite();
  const first = await snapshot(directory);
  await buildSite();
  assert.deepEqual(first, await snapshot(directory));
  assert.ok(".nojekyll" in first);
  assert.ok("index.html" in first);
  assert.equal(Object.keys(first).filter(name => name.endsWith(".html")).length, 9);
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
  assert.deepEqual(JSON.parse(await readFile(path.join(root, "docs/assets/tokens.json"), "utf8")), api.tokens);
  const meta = JSON.parse(await readFile(path.join(toolRoot, ".build/browser-metafile.json"), "utf8"));
  assert.ok(Object.keys(meta.inputs).length > 0);
  assert.ok(Object.keys(meta.inputs).every((name) => !name.includes("colorjs.io")));
  // Historical design/browser suites run serially after this test; explicit dev fixture.
  await buildSite({ dev: true });
});
