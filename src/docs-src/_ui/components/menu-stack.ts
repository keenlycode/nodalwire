import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

/** SSR-authored native navigation/disclosures; no destinations or application roles. */
export class MenuStack extends Base {
  static { this.css = componentStyles.menuStack; }
}
