import { test } from "node:test";
import assert from "node:assert/strict";
import { api } from "../../../helpers/docs-token-api.mjs";

test("WCAG sRGB contrast is symmetric, bounded, and rejects unresolved colors", () => {
  assert.equal(api.contrast("#000000", "#ffffff"), 21);
  assert.equal(api.contrast("#ffffff", "#000000"), 21);
  assert.equal(api.contrast("#123456", "#123456"), 1);
  assert.throws(() => api.contrast("blue", "#ffffff"));
  assert.throws(() => api.contrast("#fff", "#ffffff"));
  assert.ok(api.reviewData(api.tokens).pairs.every((pair) => pair.pass));
})
test("the review rejects a low-contrast palette rather than falsely labeling it AA", () => {
  const unreadable = api.createTokens({ ...api.tokens.palette, "dark.4": "#ffffff" });
  assert.throws(() => api.reviewData(unreadable), /4\.5:1/);
})
