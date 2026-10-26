import { test } from "node:test";
import assert from "node:assert/strict";
import { api } from "../../../../helpers/docs-token-api.mjs";

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
  assert.deepEqual(api.createLift(), api.tokens.lift);
  const changed = api.createTokens({ ...api.tokens.palette, "dark.4": "#123456" });
  assert.equal(changed.lift[0], "none");
  assert.equal(changed.lift[1], "drop-shadow(0 1px 2px #12345633)");
  assert.equal(changed.lift[5], "drop-shadow(0 12px 18px #1234563d)");
  assert.equal(api.tokens.palette["dark.4"], ink);
})
test("lift refuses invalid alpha-appending inputs instead of emitting invalid CSS", () => {
  for (const value of ["#fff", "rgb(36 31 49)", "not-a-color"]) {
    assert.throws(
      () => api.createLift({ ...api.tokens.palette, "dark.4": value }),
      /six-digit sRGB hex/,
    );
  }
})
