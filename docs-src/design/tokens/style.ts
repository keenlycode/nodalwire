import type { Tokens } from "../../_ui/tokens";

export default function styles(t: Tokens): string {
  return `
.token-topics { display:grid; grid-template-columns:repeat(3,minmax(0,1fr)); gap:${t.spacing.lg}; margin-top:${t.spacing.xl}; }
.token-topic { display:block; min-width:0; color:inherit; text-decoration:none; border-radius:${t.radius.md}; }
.token-topic > nw-card { height:100%; grid-template-rows:auto auto 1fr; gap:${t.spacing.md}; }
.token-topic h2 { margin:0; font-size:1.125rem; color:${t.palette["blue.5"]}; }
.token-topic p { margin:0; color:${t.colors.muted.value}; font-size:.875rem; }
.token-topic:hover h2 { text-decoration:underline; text-underline-offset:.2em; }
.token-topic:focus-visible { outline:3px solid ${t.palette["blue.5"]}; outline-offset:3px; }
.token-topic-preview { min-width:0; height:6rem; display:flex; align-items:center; justify-content:center; gap:${t.spacing.sm}; padding:${t.spacing.sm} ${t.spacing.md}; background:${t.colors.note.value}; border-radius:${t.radius.sm}; }
.token-preview-color > span { width:1.75rem; height:1.75rem; flex:0 1 1.75rem; border-radius:${t.radius.full}; }
.token-preview-type { flex-direction:column; gap:${t.spacing.xs}; }
.token-preview-type > span { font-family:${t.typography.family}; font-size:${t.typography.h1}; font-weight:700; line-height:${t.typography.headingLineHeight}; }
.token-preview-type > code { font-family:${t.typography.mono}; font-size:.75rem; }
.token-preview-spacing { flex-direction:column; align-items:flex-start; padding-inline:${t.spacing.xl}; gap:${t.spacing.xs}; }
.token-preview-spacing > span { display:block; max-width:100%; height:.375rem; flex-shrink:0; background:${t.palette["blue.5"]}; border-radius:${t.radius.full}; }
.token-preview-radius > span { width:2.5rem; height:2.5rem; flex:0 1 2.5rem; background:${t.colors.surface.value}; border:1px solid ${t.palette["blue.5"]}; }
.token-preview-layout { width:10rem; max-width:min(100%,${t.layout.reading}); display:grid; grid-template-columns:minmax(0,1fr) minmax(0,2fr); gap:${t.spacing.sm}; }
.token-preview-layout > span { min-height:2.5rem; background:${t.palette["blue.1"]}; border-radius:${t.radius.sm}; }
.token-preview-layout > span:first-child { grid-column:1/-1; min-height:.75rem; background:${t.palette["blue.5"]}; }
.token-preview-lift > span { display:block; width:5rem; height:3rem; border:1px solid ${t.colors.border.value}; border-radius:${t.radius.md}; background:${t.colors.surface.value}; }
.token-overview-download { margin-top:${t.spacing.xl}; font-size:.875rem; }
@media(max-width:850px) { .token-topics { grid-template-columns:repeat(2,minmax(0,1fr)); } }
@media(max-width:560px) { .token-topics { grid-template-columns:minmax(0,1fr); } .token-topic-preview { height:5.5rem; } }
.swatches {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 1rem;
}
.swatch {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: ${t.radius.md};
  overflow: hidden;
}
.paint {
  height: 4.5rem;
  border-bottom: 1px solid var(--border);
}
.swatch-info {
  padding: .85rem;
}
.swatch code {
  font-size: .8rem;
}
.swatch p {
  font-size: .8rem;
  margin: .35rem 0;
  color: var(--muted);
}
.source {
  font-size: .7rem;
  color: var(--muted);
}
code,
pre,
.mono {
  font-family: ${t.typography.mono};
}
code {
  overflow-wrap: anywhere;
}
p code {
  background: var(--canvas);
  padding: .1rem .3rem;
  border-radius: ${t.radius.sm};
}
.pairs {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: .75rem;
  margin-top: 1rem;
}
.pair {
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: ${t.radius.sm};
  display: flex;
  justify-content: space-between;
  gap: .75rem;
}
.pair strong {
  font-family: ${t.typography.mono};
  font-size: .8rem;
}
.pass {
  color: #17633e;
  font-size: .75rem;
}
.fine {
  font-size: .8rem;
  color: var(--muted);
}
.panel {
  padding: 1.5rem;
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: ${t.radius.md};
  min-width: 0;
}
.type-row {
  display: grid;
  grid-template-columns: 8rem minmax(0, 1fr);
  align-items: baseline;
  gap: 1.5rem;
  padding: 1.1rem 0;
  border-bottom: 1px solid var(--border);
}
.type-meta {
  font: .7rem ${t.typography.mono};
  color: var(--muted);
}
.type-row:last-child {
  border: 0;
}
.type-row p {
  margin: 0;
}
.controls {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: .8rem;
  margin: 1rem 0;
}
.controls label {
  font-size: .85rem;
}
.controls input {
  accent-color: var(--accent);
  max-width: 100%;
}
.geometry {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 1rem;
}
.space-row {
  display: flex;
  gap: 1rem;
  align-items: center;
  margin: 1.1rem 0;
}
.space-row code {
  width: 6rem;
  font-size: .75rem;
  flex-shrink: 0;
}
.bar {
  height: .65rem;
  background: var(--accent);
  border-radius: 2px;
}
.corners {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 1rem;
}
.corner {
  border: 1px solid var(--controlBorder);
  background: var(--canvas);
  height: 4.5rem;
  display: grid;
  place-items: center;
  font: .7rem ${t.typography.mono};
}
.specimen {
  display: grid;
  grid-template-columns: 11rem minmax(0, 1fr);
  padding: 0;
  overflow: hidden;
}
.specimen aside {
  background: var(--canvas);
  padding: 1.5rem;
  border-right: 1px solid var(--border);
}
.specimen aside span {
  display: block;
  padding: .6rem;
  font-size: .8rem;
}
.specimen aside .active {
  background: white;
  color: var(--accent);
  border-radius: ${t.radius.sm};
  font-weight: 600;
}
.article {
  padding: 2rem;
  min-width: 0;
}
.article h2 {
  font-size: 1.875rem;
}
.article p {
  font-size: .95rem;
}
.article pre {
  white-space: pre;
  overflow: auto;
  background: var(--code);
  color: #f6f5f4;
  padding: 1.2rem;
  margin: 0;
  font-size: .8rem;
  line-height: 1.7;
}
.code-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  background: var(--code);
  color: #deddda;
  padding: .7rem 1.2rem;
  border-bottom: 1px solid #5e5c64;
  font: .7rem ${t.typography.mono};
}
.code-box {
  border-radius: ${t.radius.md};
  overflow: hidden;
  margin: 1.4rem 0;
}
.warning {
  background: var(--warning);
  color: var(--warningInk);
  border-left: 3px solid #c64600;
  padding: 1rem 1.2rem;
}
.warning p {
  margin: .4rem 0 0;
}
.code-head button {
  background: transparent;
  color: white;
  border-color: #9a9996;
  min-height: 2rem;
  padding: .2rem .6rem;
}
.states {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  margin-top: 1.2rem;
}
.state-label {
  font-size: .7rem;
  color: var(--muted);
  margin-top: .7rem;
}
.review-prompts {
  padding-left: 1.2rem;
}
.review-prompts li {
  padding: .3rem 0;
}
@media (max-width: 1050px) {
  .swatches {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
  .geometry {
    grid-template-columns: 1fr;
  }
  .specimen {
    grid-template-columns: 1fr;
  }
  .specimen aside {
    display: none;
  }
  .pairs {
    grid-template-columns: 1fr;
  }
}
@media (max-width: 700px) {
  .type-row {
    grid-template-columns: 1fr;
    gap: .5rem;
  }
  .article {
    padding: 1.2rem;
  }
  .swatches {
    gap: .6rem;
  }
  .swatch-info {
    padding: .65rem;
  }
  .corners {
    gap: .5rem;
  }
  .pair {
    flex-wrap: wrap;
  }
  .panel {
    padding: 1rem;
  }
}
.palette-families {
  display: grid;
  gap: 1.5rem;
}
.palette-family {
  background: var(--surface);
  padding: 1rem;
  border: 1px solid var(--border);
  border-radius: .75rem;
}
.palette-family h3 {
  font-size: 1rem;
  margin: 0 0 .8rem;
  text-transform: capitalize;
  letter-spacing: 0;
}
.palette-shades {
  display: grid;
  grid-template-columns: repeat(5, minmax(0, 1fr));
  gap: .65rem;
}
.palette-chip {
  min-width: 0;
}
.palette-color {
  height: 4.5rem;
  border: 1px solid rgba(0, 0, 0, .12);
  border-radius: .25rem;
}
.palette-chip code {
  display: block;
  font-size: .72rem;
  margin-top: .45rem;
}
.palette-chip span {
  display: block;
  font-family: var(--palette-mono,ui-monospace,monospace);
  font-size: .7rem;
  color: var(--muted);
  margin-top: .15rem;
}
.palette-legend {
  display: flex;
  justify-content: space-between;
  font-size: .75rem;
  color: var(--muted);
  margin-bottom: .8rem;
}
@media (max-width: 700px) {
  .palette-family {
    padding: .8rem;
  }
  .palette-shades {
    gap: .4rem;
  }
  .palette-color {
    height: 3.5rem;
  }
  .palette-chip code {
    font-size: .63rem;
  }
  .palette-chip span {
    font-size: .61rem;
  }
}
/* Lift specimens use the same geometry; only their SSR filter values differ. */
.lift-grid {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: ${t.spacing.xl};
  padding: ${t.spacing.sm} 0 ${t.spacing.md};
}
.lift-specimen { min-width: 0; }
.lift-surface {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: ${t.radius.md};
  padding: 1.2rem;
  min-width: 0;
}
.lift-specimen .lift-surface {
  min-height: 9rem;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
}
.lift-surface h3 { font-size: 1.05rem; margin: .6rem 0; }
.lift-surface p { font-size: .85rem; color: var(--muted); margin: .5rem 0; }
.lift-label { font: .75rem ${t.typography.mono}; color: var(--accent); }
.lift-caption { margin: 1rem .1rem .3rem; font-size: .8rem; }
.lift-recipe {
  display: block;
  font: .7rem/1.5 ${t.typography.mono};
  overflow-wrap: anywhere;
  color: var(--muted);
}
.lift-playground {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(0, 1.7fr);
  gap: ${t.spacing.xl};
  margin-top: 2rem;
}
.lift-controls label { display: block; font-size: .85rem; margin-top: 1rem; }
.lift-controls output { float: right; font-family: ${t.typography.mono}; }
.lift-controls input[type=range] { width: 100%; accent-color: var(--accent); margin: .8rem 0; }
.lift-controls .lift-check { display: flex; align-items: center; gap: .5rem; }
.lift-check input { accent-color: var(--accent); width: 1rem; height: 1rem; }
#lift-active-recipe { margin-top: 1rem; }
.lift-stage {
  background: var(--note);
  border: 1px solid var(--border);
  border-radius: ${t.radius.lg};
  padding: 2rem;
  display: grid;
  gap: ${t.spacing.xl};
  align-content: center;
}
.lift-stage .lift-surface h3 { font-size: 1.3rem; }
.lift-silhouette { text-align: center; }
#lift-shape { display: inline-flex; gap: 1rem; align-items: center; padding: .5rem; }
.lift-circle, .lift-square { display: block; width: 2.5rem; height: 2.5rem; }
.lift-circle { background: var(--accent); border-radius: 50%; }
.lift-square { background: var(--warningInk); border-radius: .4rem; }
#lift.lift-no-borders .lift-surface { border-color: transparent; }
@media (max-width: 1050px) {
  .lift-grid { grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 1.3rem; }
  .lift-playground { grid-template-columns: 1fr; }
}
@media (max-width: 700px) {
  .lift-grid { gap: 1rem; }
  .lift-surface { padding: 1rem; }
  .lift-stage { padding: 1.5rem; }
}
`;
}
