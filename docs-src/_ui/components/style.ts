import type { Tokens } from "../tokens";
import { componentRecipes } from "./recipes";

/** Progressive-enhancement fallback, generated from the same recipes as Adapter. */
export default (tokens: Tokens) => {
  const { base, button, buttonPin, card, iconButton, codeBlock, topNavigation, bottomNavigation, menuStack, link, badge, inlineCode } = componentRecipes(tokens);
  return `nw-button { ${base} ${button} }\nnw-button-pin { ${base} ${button} ${buttonPin} }\nnw-card { ${base} ${card} }\nnw-icon-button { ${base} ${button} ${iconButton} }\nnw-code-block { ${base} ${codeBlock} }\nnw-top-navigation { ${base} ${topNavigation} }\nnw-bottom-navigation { ${base} ${bottomNavigation} }\nnw-menu-stack { ${base} ${menuStack} }\nnw-link { ${base} ${link} }\nnw-badge { ${base} ${badge} }\nnw-inline-code { ${base} ${inlineCode} }`;
};
