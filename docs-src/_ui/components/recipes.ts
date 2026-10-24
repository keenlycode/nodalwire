import type { Tokens } from "../tokens";

/** One token-derived recipe for Adapter class CSS and the no-JS fallback. Build-only. */
export function componentRecipes(t: Tokens) {
  return {
    base: `box-sizing:border-box; font-family:${t.typography.family}; line-height:${t.typography.lineHeight}; color:${t.palette["dark.4"]};`,
    button: `display:inline-flex; vertical-align:middle; max-width:100%;
      & > button { box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; min-height:2.25rem; max-width:100%; margin:0; border:1px solid ${t.palette["blue.5"]}; border-radius:${t.radius.md}; padding:${t.spacing.sm} ${t.spacing.md}; background:${t.palette["blue.5"]}; color:${t.palette["light.1"]}; font:inherit; font-size:.875rem; font-weight:500; line-height:1.25; text-align:center; overflow-wrap:anywhere; cursor:pointer; }
      & > button:hover:not(:disabled) { background:${t.palette["dark.4"]}; border-color:${t.palette["dark.4"]}; }
      & > button:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:3px; }
      & > button:disabled { background:${t.palette["light.3"]}; border-color:${t.palette["light.4"]}; color:${t.palette["dark.2"]}; cursor:not-allowed; }`,
    buttonPin: `& > button { width:2.75rem; height:2.75rem; min-height:2.75rem; padding:0; border-radius:50%; font-size:.75rem; }`,
    iconButton: `& > button { width:2.25rem; height:2.25rem; padding:${t.spacing.sm}; flex-shrink:0; } & > button > svg { display:block; width:1rem; height:1rem; }`,
    codeBlock: `display:grid; grid-template-columns:1fr auto; gap:${t.spacing.sm}; min-width:0; padding:${t.spacing.md}; border:1px solid ${t.palette["light.4"]}; border-radius:${t.radius.md}; background:${t.palette["light.2"]};
      & > pre { grid-column:1 / -1; margin:0; min-width:0; max-width:100%; overflow:auto; padding:${t.spacing.sm}; font-size:.875rem; line-height:1.6; tab-size:2; }
      & > pre > code { font-family:ui-monospace,monospace; white-space:pre; }
      & > nw-icon-button { grid-column:2; grid-row:2; }
      & > output { grid-column:1; grid-row:2; align-self:center; font-size:.875rem; overflow-wrap:anywhere; }`,
    topNavigation: `display:block; position:static; background:${t.palette["light.1"]}; border-bottom:1px solid ${t.palette["light.4"]}; padding:${t.spacing.lg};
      & > .navigation-inner { max-width:80rem; margin:auto; }
      & .navigation-brand { display:block; font-weight:700; margin-bottom:${t.spacing.md}; }
      & nav { position:static; margin:0; display:block; }
      & ul { display:flex; flex-wrap:wrap; gap:${t.spacing.sm}; list-style:none; padding:0; margin:0; }
      & a { display:block; padding:${t.spacing.sm} ${t.spacing.md}; border:0; border-radius:${t.radius.sm}; color:${t.palette["dark.4"]}; text-decoration:none; }
      & a:hover, & a[aria-current=page] { background:${t.palette["light.2"]}; color:${t.palette["blue.5"]}; }
      & a:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:2px; }`,
    bottomNavigation: `display:block; position:fixed; inset:auto 0 0; z-index:5; background:${t.palette["light.1"]}; border-top:1px solid ${t.palette["light.4"]}; padding-bottom:env(safe-area-inset-bottom,0px);
      & > details > summary { box-sizing:border-box; min-height:3.5rem; padding:${t.spacing.md} ${t.spacing.lg}; cursor:pointer; color:${t.palette["dark.4"]}; font-weight:500; }
      & > details > summary:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:-4px; }
      & > details > .navigation-panel { position:absolute; bottom:100%; left:0; right:0; max-height:calc(100vh - 6rem - env(safe-area-inset-bottom,0px)); max-height:calc(100dvh - 6rem - env(safe-area-inset-bottom,0px)); overflow:auto; overscroll-behavior:contain; background:${t.palette["light.1"]}; border-top:1px solid ${t.palette["light.4"]}; padding:${t.spacing.md} ${t.spacing.lg}; }
      & nav { position:static; margin:0; display:block; }
      & ul { display:grid; grid-template-columns:repeat(auto-fit,minmax(min(100%,14rem),1fr)); gap:${t.spacing.sm}; max-width:80rem; margin:0 auto; padding:0; list-style:none; }
      & a { display:block; padding:${t.spacing.md}; border:0; border-radius:${t.radius.sm}; color:${t.palette["dark.4"]}; text-decoration:none; }
      & a:hover, & a[aria-current=page] { background:${t.palette["light.2"]}; color:${t.palette["blue.5"]}; }
      & a:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:-2px; }`,
    menuStack: `display:block; height:var(--nw-menu-stack-height,100vh); height:var(--nw-menu-stack-height,100dvh); min-width:0; max-width:100%; overflow-y:auto; overflow-x:hidden; overscroll-behavior:contain; background:${t.palette["light.1"]};
      &[hidden] { display:none !important; }
      & nav { position:static; display:block; margin:0; }
      & ul { display:block; list-style:none; margin:0; padding:0; }
      & li { min-width:0; }
      & li li { padding-inline-start:${t.spacing.md}; }
      & a { display:block; padding:${t.spacing.sm} ${t.spacing.md}; border-radius:${t.radius.sm}; color:${t.palette["dark.4"]}; text-decoration:none; overflow-wrap:anywhere; }
      & a:hover, & a[aria-current=page] { background:${t.palette["light.2"]}; color:${t.palette["blue.5"]}; }
      & [data-current-parent] > a { font-weight:700; }
      & summary { display:flex; align-items:center; justify-content:space-between; gap:${t.spacing.md}; padding:${t.spacing.sm} ${t.spacing.md}; cursor:pointer; font-weight:500; list-style:none; }
      & summary::-webkit-details-marker { display:none; }
      & summary::marker { content:""; }
      & .menu-stack-toggle { flex:0 0 auto; font-weight:700; }
      & .when-open { display:none; }
      & .when-closed { display:inline; }
      & details[open] > summary .when-open { display:inline; }
      & details[open] > summary .when-closed { display:none; }
      & a:focus-visible, & summary:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:-2px; }`,
    link: `display:inline; & > a { color:${t.palette["blue.5"]}; text-decoration:underline; text-underline-offset:.2em; overflow-wrap:anywhere; } & > a:hover { color:${t.palette["dark.4"]}; } & > a:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:3px; }`,
    badge: `display:inline-flex; align-items:center; max-width:100%; padding:.125em .5em; border:1px solid ${t.palette["light.4"]}; border-radius:${t.radius.sm}; background:${t.palette["light.3"]}; color:${t.palette["dark.4"]}; font-size:.8125rem; font-weight:500; line-height:1.5; vertical-align:baseline; overflow-wrap:anywhere;`,
    inlineCode: `display:inline; & > code { padding:.125em .375em; border:1px solid ${t.palette["light.4"]}; border-radius:${t.radius.sm}; background:${t.palette["light.2"]}; color:${t.palette["dark.4"]}; font-family:${t.typography.mono}; font-size:.875em; white-space:break-spaces; overflow-wrap:anywhere; box-decoration-break:clone; -webkit-box-decoration-break:clone; }`,
    card: `display:grid; gap:${t.spacing.md}; padding:${t.spacing.lg}; border:1px solid ${t.palette["light.4"]}; border-radius:${t.radius.md}; background:${t.palette["light.1"]}; color:${t.palette["dark.4"]}; min-width:0; overflow-wrap:anywhere;
      & > :first-child { margin-top:0; } & > :last-child { margin-bottom:0; }`,
  };
}
