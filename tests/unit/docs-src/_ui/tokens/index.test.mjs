import { test } from "node:test";
import assert from "node:assert/strict";
import { api } from "../../../../helpers/docs-token-api.mjs";

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
})
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
})
test("a palette edit flows through both a direct alias and a derived tint without mutating the base", () => {
  const original = structuredClone(api.tokens.palette);
  const values = { ...original, "blue.5": "#215599", "blue.3": "#d85599" };
  const changed = api.createTokens(values);
  assert.equal(changed.colors.accent.value, values["blue.5"]);
  assert.notEqual(changed.colors.note.value, api.tokens.colors.note.value);
  assert.equal(changed.colors.warning.value, api.tokens.colors.warning.value);
  assert.deepEqual(api.tokens.palette, original);
  for (const value of ["#fff", "rgb(36 31 49)", "not-a-color"]) {
    assert.throws(
      () => api.createTokens({ ...api.tokens.palette, "dark.4": value }),
      /six-digit sRGB hex/,
    );
  }
})
