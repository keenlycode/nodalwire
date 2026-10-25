import { palette, type Palette } from "./palette";
import { createSemanticColors } from "./semantic";
import { typography } from "./typography";
import { spacing } from "./spacing";
import { radius } from "./radius";
import { layout } from "./layout";
import { createLift } from "./lift";

export function createTokens(values: Palette = palette) {
  return {
    palette: values, colors: createSemanticColors(values),
    typography, spacing, radius, layout, lift: createLift(values),
  };
}

export const tokens = createTokens();
export type Tokens = ReturnType<typeof createTokens>;
