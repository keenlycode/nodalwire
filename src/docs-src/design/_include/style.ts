import type { Tokens } from "../../_ui/tokens";
/** Only the enhanced design composition floats; SSR navigation stays reachable. */
export default (t: Tokens) => `
body { padding-bottom:calc(5rem + env(safe-area-inset-bottom,0px)); }
.design-page-main { padding-block:${t.spacing.xl} ${t.spacing.section}; }
.page-header { position:static; top:auto; z-index:auto; background:transparent; border:0; }
.page-toc nav { position:static; display:flex; flex-wrap:wrap; gap:${t.spacing.sm}; margin-block:${t.spacing.md}; }
.page-toc .eyebrow { flex-basis:100%; }
.design-navigation > nw-button-pin[hidden] { display:none; }
.design-menu-panel { display:flex; flex-direction:column; box-sizing:border-box; padding:${t.spacing.sm}; overflow:hidden; border:1px solid ${t.palette["light.4"]}; border-radius:${t.radius.lg}; background:${t.palette["light.1"]}; }
.design-menu-panel[hidden] { display:none; }
.design-menu-heading { flex:none; margin:calc(-1 * ${t.spacing.sm}) calc(-1 * ${t.spacing.sm}) 0; padding:calc(2 * ${t.spacing.sm}) calc(2 * ${t.spacing.md}) ${t.spacing.sm}; border-bottom:1px solid ${t.colors.border.value}; background:${t.colors.note.value}; color:${t.palette["blue.5"]}; font-size:1rem; font-weight:700; line-height:1.4; }
.design-menu-heading a { display:inline-block; color:inherit; text-decoration:none; border-radius:${t.radius.sm}; }
.design-menu-heading a:hover { color:${t.palette["blue.5"]}; text-decoration:underline; text-underline-offset:.2em; }
.design-menu-heading a:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:2px; }
.design-menu-scroll { --nw-menu-stack-height:auto; min-height:0; padding:calc(${t.spacing.md} - ${t.spacing.sm}); overflow-y:auto; overflow-x:hidden; overscroll-behavior:contain; scrollbar-width:thin; scrollbar-color:${t.palette["light.5"]} transparent; }
.design-menu-panel nav > ul > li + li { margin-top:${t.spacing.md}; padding-top:${t.spacing.md}; border-top:1px solid ${t.palette["light.3"]}; }
.design-menu-panel .design-group { position:relative; }
.design-menu-panel nav > ul > li + li > a { top:${t.spacing.md}; }
.design-menu-panel nav > ul > li > a { position:absolute; top:0; left:0; right:2.75rem; min-height:2.75rem; display:flex; align-items:center; font-weight:700; font-size:.9375rem; }
.design-menu-panel [data-current-parent] > a { color:${t.palette["blue.5"]}; }
.design-menu-panel .design-group > details > summary { width:2.75rem; padding:0; margin-inline-start:auto; justify-content:center; }
.design-group-chevron { display:flex; align-items:center; justify-content:center; }
.design-group-chevron > svg { width:1rem; height:1rem; }
.design-group > details[open] > summary .design-group-chevron { transform:rotate(90deg); }
.design-navigation > nw-button-pin > button > svg { width:1.25rem; height:1.25rem; }
.design-menu-panel summary { min-height:2.75rem; font-size:.8125rem; color:${t.palette["dark.2"]}; border-radius:${t.radius.sm}; }
.design-menu-panel summary:hover { background:${t.palette["light.2"]}; color:${t.palette["dark.4"]}; }
.design-menu-panel nav ul ul { margin-inline-start:${t.spacing.md}; border-inline-start:1px solid ${t.palette["light.4"]}; }
.design-menu-panel nav li li { padding-inline-start:${t.spacing.sm}; }
.design-menu-panel nav li li a { min-height:2.5rem; display:flex; align-items:center; font-size:.875rem; }
.design-menu-panel a[aria-current=page] { color:${t.palette["blue.5"]}; background:${t.palette["light.2"]}; font-weight:700; box-shadow:inset 3px 0 ${t.palette["blue.5"]}; }
.design-navigation[data-enhanced] { position:fixed; z-index:5; left:calc(1rem + env(safe-area-inset-left,0px)); bottom:calc(1rem + env(safe-area-inset-bottom,0px)); }
.design-navigation[data-enhanced] > nw-button-pin { display:inline-flex; filter:${t.lift[2]}; }
.design-navigation[data-enhanced] > .design-menu-panel { position:absolute; bottom:calc(100% + .75rem); left:0; width:21rem; max-width:calc(100vw - 2rem - env(safe-area-inset-left,0px) - env(safe-area-inset-right,0px)); max-height:calc(100vh - 6.5rem - env(safe-area-inset-bottom,0px) - env(safe-area-inset-top,0px)); max-height:calc(100dvh - 6.5rem - env(safe-area-inset-bottom,0px) - env(safe-area-inset-top,0px)); filter:${t.lift[3]}; }
`;
