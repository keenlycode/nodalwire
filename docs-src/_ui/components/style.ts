import type { Tokens } from "../tokens";
import { componentRecipes } from "./recipes";

/** Progressive-enhancement fallback, generated from the same recipes as Adapter. */
export default (tokens: Tokens) => {
  const { base, button, card } = componentRecipes(tokens);
  return `nw-button { ${base} ${button} }\nnw-card { ${base} ${card} }`;
};
