import assert from "node:assert/strict";
import { test } from "node:test";
import { build } from "esbuild";
import { readFile, readdir } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { buildSite } from "../build.mjs";

const toolRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const root = path.resolve(toolRoot, "../..");
const bundle = await build({
  stdin: {
    contents: [
      `export { createTokens, tokens } from ${JSON.stringify(path.join(root, "docs-src/_ui/tokens/index.ts"))};`,
      `export { contrast, reviewData } from ${JSON.stringify(path.join(toolRoot, "review-data.ts"))};`,
    ].join("\n"),
    resolveDir: toolRoot,
    loader: "ts",
  },
  bundle: true,
  platform: "node",
  format: "esm",
  write: false,
  nodePaths: [path.join(toolRoot, "node_modules")],
});
const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);

test("palette has ten complete five-shade families; only pink is an extension", () => {
  const data = api.reviewData(api.tokens);
  assert.equal(Object.keys(api.tokens.palette).length, 50);
  assert.equal(data.families.length, 10);
  assert.deepEqual(data.families.filter((family) => family.extension).map((family) => family.name), ["pink"]);
  for (const family of data.families) {
    assert.equal(family.shades.length, 5);
    assert.deepEqual(family.shades.map((shade) => shade.name), [1, 2, 3, 4, 5].map((shade) => `${family.name}.${shade}`));
    for (const shade of family.shades) assert.match(shade.value, /^#[0-9a-f]{6}$/i);
  }
});

test("semantic aliases refer to the supplied palette and tint recipes have valid inputs", () => {
  for (const color of Object.values(api.tokens.colors)) {
    assert.ok(color.recipe.key in api.tokens.palette);
    if (color.recipe.kind === "palette") {
      assert.equal(color.value, api.tokens.palette[color.recipe.key]);
    } else {
      assert.ok(color.recipe.whiteFraction > 0 && color.recipe.whiteFraction < 1);
      assert.ok(color.recipe.white in api.tokens.palette);
      assert.equal(color.recipe.space, "oklch");
      assert.match(color.value, /^#[0-9a-f]{6}$/i);
    }
  }
});

test("a palette edit flows through both a direct alias and a derived tint without mutating the base", () => {
  const original = structuredClone(api.tokens.palette);
  const values = { ...original, "blue.5": "#215599", "blue.3": "#d85599" };
  const changed = api.createTokens(values);
  assert.equal(changed.colors.accent.value, values["blue.5"]);
  assert.notEqual(changed.colors.note.value, api.tokens.colors.note.value);
  assert.equal(changed.colors.warning.value, api.tokens.colors.warning.value);
  assert.deepEqual(api.tokens.palette, original);
});

test("lift retains Adaptive's exact six recipes and follows palette shadow ink", () => {
  const ink = api.tokens.palette["dark.4"];
  assert.deepEqual(api.tokens.lift, {
    0: "none",
    1: `drop-shadow(0 1px 2px ${ink}33)`,
    2: `drop-shadow(0 2px 4px ${ink}3d)`,
    3: `drop-shadow(0 4px 7px ${ink}3d)`,
    4: `drop-shadow(0 8px 12px ${ink}3d)`,
    5: `drop-shadow(0 12px 18px ${ink}3d)`,
  });
  const changed = api.createTokens({ ...api.tokens.palette, "dark.4": "#123456" });
  assert.equal(changed.lift[0], "none");
  assert.equal(changed.lift[1], "drop-shadow(0 1px 2px #12345633)");
  assert.equal(changed.lift[5], "drop-shadow(0 12px 18px #1234563d)");
  assert.equal(api.tokens.palette["dark.4"], ink);
});

test("lift refuses invalid alpha-appending inputs instead of emitting invalid CSS", () => {
  for (const value of ["#fff", "rgb(36 31 49)", "not-a-color"]) {
    assert.throws(
      () => api.createTokens({ ...api.tokens.palette, "dark.4": value }),
      /six-digit sRGB hex/,
    );
  }
});

test("WCAG sRGB contrast is symmetric, bounded, and rejects unresolved colors", () => {
  assert.equal(api.contrast("#000000", "#ffffff"), 21);
  assert.equal(api.contrast("#ffffff", "#000000"), 21);
  assert.equal(api.contrast("#123456", "#123456"), 1);
  assert.throws(() => api.contrast("blue", "#ffffff"));
  assert.throws(() => api.contrast("#fff", "#ffffff"));
  assert.ok(api.reviewData(api.tokens).pairs.every((pair) => pair.pass));
});

test("the review rejects a low-contrast palette rather than falsely labeling it AA", () => {
  const unreadable = api.createTokens({ ...api.tokens.palette, "dark.4": "#ffffff" });
  assert.throws(() => api.reviewData(unreadable), /4\.5:1/);
});

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
});
