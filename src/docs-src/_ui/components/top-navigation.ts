import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

/** Ordinary-flow container. Navigation content stays authored native HTML. */
export class TopNavigation extends Base {
  static { this.css = componentStyles.topNavigation; }
}
