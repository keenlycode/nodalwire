import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

/** Native caller-authored location links; no routing or generated content. */
export class PagePath extends Base {
  static { this.css = componentStyles.pagePath; }
}
