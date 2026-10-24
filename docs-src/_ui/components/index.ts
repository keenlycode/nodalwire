import { Button } from "./button";
import { ButtonPin } from "./button-pin";
import { Card } from "./card";
export { Base } from "./base";
import { IconButton } from "./icon-button";
import { CodeBlock } from "./code-block";
import { TopNavigation } from "./top-navigation";
import { BottomNavigation } from "./bottom-navigation";
import { Link } from "./link";
import { Badge } from "./badge";
import { InlineCode } from "./inline-code";
import { MenuStack } from "./menu-stack";
export { Button, ButtonPin, Card, IconButton, CodeBlock, TopNavigation, BottomNavigation, Link, Badge, InlineCode, MenuStack };
export function registerComponents(): void {
  Button.define("nw-button");
  ButtonPin.define("nw-button-pin");
  Card.define("nw-card");
  IconButton.define("nw-icon-button");
  CodeBlock.define("nw-code-block");
  TopNavigation.define("nw-top-navigation");
  BottomNavigation.define("nw-bottom-navigation");
  Link.define("nw-link");
  Badge.define("nw-badge");
  InlineCode.define("nw-inline-code");
  MenuStack.define("nw-menu-stack");
}
