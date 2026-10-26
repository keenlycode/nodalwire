import type { Tokens } from "../../docs-src/_ui/tokens";
import { paletteExtensions } from "../../docs-src/_ui/tokens/palette";

export function luminance(hex: string): number {
  if (!/^#[0-9a-f]{6}$/i.test(hex)) {
    throw new Error(`Expected a resolved six-digit sRGB hex color: ${hex}`);
  }
  const channels = [1, 3, 5].map((offset) => {
    const channel = parseInt(hex.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.04045 ? channel / 12.92 : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return channels[0] * 0.2126 + channels[1] * 0.7152 + channels[2] * 0.0722;
}

export function contrast(first: string, second: string): number {
  const light = luminance(first);
  const dark = luminance(second);
  return (Math.max(light, dark) + 0.05) / (Math.min(light, dark) + 0.05);
}

/** Display data is derived from canonical tokens, never a second color definition. */
export function reviewData(tokens: Tokens) {
  const families = new Map<string, {
    name: string;
    extension: boolean;
    shades: { name: string; value: string }[];
  }>();
  for (const [name, value] of Object.entries(tokens.palette)) {
    const family = name.split(".")[0];
    if (!families.has(family)) {
      families.set(family, { name: family, extension: paletteExtensions.has(family), shades: [] });
    }
    families.get(family)!.shades.push({ name, value });
  }

  const pairDefinitions = [
    ["ink", "surface", "Body / surface"],
    ["muted", "surface", "Secondary / surface"],
    ["accent", "surface", "Link / surface"],
    ["surface", "accent", "Action label / accent"],
    ["warningInk", "warning", "Warning text / warning"],
    ["surface", "code", "Code text / code"],
  ] as const;
  const pairs = pairDefinitions.map(([foreground, background, title]) => {
    const ratio = contrast(tokens.colors[foreground].value, tokens.colors[background].value);
    return { title, ratio: ratio.toFixed(2), pass: ratio >= 4.5 };
  });
  if (pairs.some((pair) => !pair.pass)) {
    throw new Error("A reviewed normal-text color pair is below WCAG AA's 4.5:1 threshold");
  }
  return { families: [...families.values()], pairs };
}
