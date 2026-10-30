import { palette, type Palette } from "./palette";

/**
 * Adaptive's painted-silhouette lift scale, for CSS `filter`, not `box-shadow`.
 * 0 adds no filter; 1–5 increase distance/softness, not z-index.
 * Nonzero filters create stacking contexts. Compose other filters in caller CSS.
 * Transparent groups lift their painted children rather than an empty box.
 */
export function createLift(values: Palette = palette) {
  const ink = values["dark.4"];
  if (!/^#[0-9a-f]{6}$/i.test(ink)) {
    throw new Error("Lift requires palette.dark.4 as a six-digit sRGB hex color");
  }
  return {
    0: "none",
    1: `drop-shadow(0 1px 2px ${ink}33)`,
    2: `drop-shadow(0 2px 4px ${ink}3d)`,
    3: `drop-shadow(0 4px 7px ${ink}3d)`,
    4: `drop-shadow(0 8px 12px ${ink}3d)`,
    5: `drop-shadow(0 12px 18px ${ink}3d)`,
  } as const;
}

export const lift = createLift();
export type LiftLevel = keyof typeof lift;
