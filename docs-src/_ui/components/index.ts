import { Button } from "./button";
import { Card } from "./card";
export { Base } from "./base";
export { Button, Card };
export function registerComponents(): void {
  Button.define("nw-button");
  Card.define("nw-card");
}
