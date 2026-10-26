import { createHighlighterCore } from "shiki/core";
import { createJavaScriptRegexEngine } from "shiki/engine/javascript";
import { palette } from "../tokens/palette";

/** Loaded only for a supported CodeBlock; no preset themes, other grammars or WASM. */
export const syntaxTheme = {
  name: "nodalwire", type: "light" as const,
  colors: { "editor.background": palette["light.1"], "editor.foreground": palette["dark.4"] },
  tokenColors: [
    { scope: ["comment"], settings: { foreground: palette["dark.2"] } },
    { scope: ["keyword", "storage"], settings: { foreground: palette["blue.5"] } },
    { scope: ["string"], settings: { foreground: palette["brown.5"] } },
    { scope: ["constant.numeric", "constant.language"], settings: { foreground: palette["red.5"] } },
    { scope: ["entity.name.function", "support.function", "entity.name.type", "support.type"], settings: { foreground: palette["purple.5"] } },
  ],
};
const highlighter = createHighlighterCore({
  themes: [syntaxTheme], langs: [], engine: createJavaScriptRegexEngine(),
});
const loaders = {
  python: () => import("shiki/langs/python.mjs"),
  javascript: () => import("shiki/langs/javascript.mjs"),
};
export type HighlightLanguage = keyof typeof loaders;
const languages = new Map<HighlightLanguage, Promise<void>>();

/** Shared engine and in-flight grammar loads across all blocks. */
export async function tokenizeCode(text: string, language: HighlightLanguage) {
  const instance = await highlighter;
  if (!languages.has(language)) {
    languages.set(language, loaders[language]().then(module => instance.loadLanguage(module.default)));
  }
  await languages.get(language);
  return instance.codeToTokens(text, { lang: language, theme: syntaxTheme.name }).tokens.flat();
}
