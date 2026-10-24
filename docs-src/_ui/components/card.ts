import { Base } from "./base";
import { componentStyles } from "./resolved-styles";

export class Card extends Base {
  static { this.css = componentStyles.card; }
  static create(options: { children?: Iterable<Node | string> } = {}): Card {
    const children = [...(options.children ?? [])];
    if (children.some(child => typeof child !== "string" && !(child instanceof Node))) throw new TypeError("Card children must be nodes or text");
    const card = new this(); card.append(...children); return card;
  }
}
