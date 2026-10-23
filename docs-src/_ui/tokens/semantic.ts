import Color from "colorjs.io";
import { palette, type Palette, type PaletteKey } from "./palette";

/** Resolve roles from the supplied palette, without mutating foundation values. */
export function createSemanticColors(values: Palette = palette) {
  function reference(key: PaletteKey, purpose: string) {
    return {
      value: values[key], purpose, source: `palette.${key}`,
      recipe: { kind: "palette" as const, key },
    };
  }

  function tint(key: PaletteKey, whiteFraction: number, purpose: string) {
    const color = new Color(values[key]).mix(values["light.1"], whiteFraction, {
      space: "oklch", outputSpace: "srgb",
    });
    color.toGamut({ space: "srgb" });
    return {
      value: color.toString({ format: "hex" }), purpose,
      source: `palette.${key} + ${Math.round(whiteFraction * 100)}% palette.light.1 · OKLCH → sRGB`,
      recipe: {
        kind: "tint" as const, key, white: "light.1" as const,
        whiteFraction, space: "oklch" as const, output: "srgb" as const,
      },
    };
  }

  return {
    canvas: reference("light.2", "Page canvas"),
    surface: reference("light.1", "Reading surfaces"),
    ink: reference("dark.4", "Primary text"),
    muted: reference("dark.2", "Secondary text"),
    border: reference("light.3", "Decorative separators; not control boundaries"),
    controlBorder: reference("dark.1", "Control boundaries"),
    accent: reference("blue.5", "Links and actions"),
    focus: reference("blue.4", "Keyboard focus ring"),
    note: tint("blue.3", 0.92, "Information surface"),
    warning: tint("orange.1", 0.78, "Warning surface"),
    warningInk: reference("brown.5", "Warning foreground"),
    code: reference("dark.4", "Code surface"),
  };
}
