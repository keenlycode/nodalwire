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

test("two standalone builds reproduce every generated file without leaking Color.js or sources", async () => {
  await buildSite();
  const first = await snapshot(path.join(root, "docs"));
  await buildSite();
  const second = await snapshot(path.join(root, "docs"));
  assert.deepEqual(first, second);
  assert.ok(".nojekyll" in first);
  assert.ok("index.html" in first);
  assert.ok("design/tokens/index.html" in first);
  assert.ok(Object.keys(first).every((name) => !/\.(ts|mjs|py|map)$/.test(name)));
  assert.deepEqual(JSON.parse(await readFile(path.join(root, "docs/assets/tokens.json"), "utf8")), api.tokens);
  const meta = JSON.parse(await readFile(path.join(toolRoot, ".build/browser-metafile.json"), "utf8"));
  assert.ok(Object.keys(meta.inputs).length > 0);
  assert.ok(Object.keys(meta.inputs).every((name) => !name.includes("colorjs.io")));
})
