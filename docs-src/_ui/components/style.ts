import type { Tokens } from "../tokens";
export default (t: Tokens) => `
nw-button { display:inline-flex; vertical-align:middle; max-width:100%; }
nw-button > button { box-sizing:border-box; display:inline-flex; align-items:center; justify-content:center; min-height:2.25rem; max-width:100%; margin:0; border:1px solid ${t.palette["blue.5"]}; border-radius:${t.radius.md}; padding:${t.spacing.sm} ${t.spacing.md}; background:${t.palette["blue.5"]}; color:${t.palette["light.1"]}; font:inherit; font-size:.875rem; font-weight:500; line-height:1.25; text-align:center; overflow-wrap:anywhere; cursor:pointer; }
nw-button > button:hover:not(:disabled) { background:${t.palette["dark.4"]}; border-color:${t.palette["dark.4"]}; }
nw-button > button:focus-visible { outline:2px solid ${t.palette["blue.5"]}; outline-offset:3px; }
nw-button > button:disabled { background:${t.palette["light.3"]}; border-color:${t.palette["light.4"]}; color:${t.palette["dark.2"]}; cursor:not-allowed; }
nw-card { display:grid; gap:${t.spacing.md}; padding:${t.spacing.lg}; border:1px solid ${t.palette["light.4"]}; border-radius:${t.radius.md}; background:${t.palette["light.1"]}; color:${t.palette["dark.4"]}; min-width:0; overflow-wrap:anywhere; }
nw-card > :first-child { margin-top:0; } nw-card > :last-child { margin-bottom:0; }
`;
