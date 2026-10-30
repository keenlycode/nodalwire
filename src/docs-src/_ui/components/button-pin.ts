import { Button } from "./button";
import { componentStyles } from "./resolved-styles";

/** Approved circular button shape; placement and menu behavior belong to callers. */
export class ButtonPin extends Button {
  static { this.css = componentStyles.buttonPin; }
}
