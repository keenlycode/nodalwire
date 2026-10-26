import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

/** Layout-only, light-DOM wrapper; semantic content remains caller-owned. */
export class Container extends Base {
  static { this.css = componentStyles.container; }
}
