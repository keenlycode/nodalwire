import type { Tokens } from "../_ui/tokens";

export default function styles(t: Tokens): string {
  const variables = Object.entries(t.colors)
    .map(([name, item]) => `  --${name}: ${item.value};`).join("\n");
  return `
:root {
${variables}
  font-size: ${t.typography.root};
  color-scheme: light;
}
* {
  box-sizing: border-box;
}
html {
  scroll-behavior: smooth;
  scroll-padding-top: 6rem;
}
body {
  margin: 0;
  background: var(--canvas);
  color: var(--ink);
  font-family: ${t.typography.family};
  line-height: ${t.typography.lineHeight};
}
a {
  color: var(--accent);
  text-underline-offset: .2em;
}
button,
input {
  font: inherit;
}
button,
a,
input {
  touch-action: manipulation;
}
:focus-visible {
  outline: 3px solid var(--focus);
  outline-offset: 4px;
}
.skip {
  position: absolute;
  top: -5rem;
  left: 1rem;
  background: white;
  padding: 1rem;
  z-index: 10;
}
.skip:focus {
  top: 1rem;
}
header {
  position: sticky;
  top: 0;
  z-index: 2;
  background: rgba(255, 255, 255, .97);
  border-bottom: 1px solid var(--border);
}
.header-inner {
  max-width: 1440px;
  margin: auto;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  padding: 1rem 2rem;
}
.brand {
  font-weight: 700;
  letter-spacing: -.035em;
  font-size: 1.2rem;
}
.brand span {
  color: var(--accent);
}
.badge {
  font: 600 .7rem ${t.typography.mono};
  padding: .35rem .6rem;
  border: 1px solid var(--border);
  border-radius: 9999px;
  letter-spacing: .02em;
  white-space: nowrap;
}
.layout {
  max-width: 1440px;
  margin: auto;
  display: grid;
  grid-template-columns: ${t.layout.sidebar} minmax(0, 1fr);
  gap: 2rem;
  padding: 2.5rem 2rem 4rem;
}
nav {
  position: sticky;
  top: 7rem;
  align-self: start;
}
nav a {
  display: block;
  padding: .6rem .8rem;
  text-decoration: none;
  color: var(--muted);
  border-left: 2px solid transparent;
}
nav a:hover,
nav a[aria-current=true] {
  background: var(--surface);
  color: var(--accent);
  border-color: var(--accent);
}
.eyebrow {
  font: .7rem ${t.typography.mono};
  letter-spacing: .1em;
  text-transform: uppercase;
  color: var(--muted);
}
h1,
h2,
h3,
h4 {
  line-height: ${t.typography.headingLineHeight};
  letter-spacing: -.035em;
}
h1 {
  font-size: ${t.typography.h1};
  margin: .6rem 0 1rem;
}
h2 {
  font-size: ${t.typography.h2};
  margin: .5rem 0;
}
h3 {
  font-size: ${t.typography.h3};
  margin: 0 0 .8rem;
}
h4 {
  margin: 0 0 .6rem;
  font-size: 1rem;
}
p {
  max-width: ${t.layout.reading};
}
.lead {
  font-size: 1.1rem;
  color: var(--muted);
}
section {
  margin-top: 3rem;
  scroll-margin-top: 7rem;
}
.section-heading {
  display: flex;
  align-items: baseline;
  justify-content: space-between;
  gap: 1rem;
  border-bottom: 1px solid var(--border);
  padding-bottom: 1rem;
  margin-bottom: 1.5rem;
}
.section-heading small {
  font-family: ${t.typography.mono};
  color: var(--muted);
}
.review-note {
  background: var(--note);
  padding: 1rem 1.3rem;
  border-left: 3px solid var(--accent);
  margin: 1.5rem 0;
}
.review-note p {
  margin: .3rem 0;
}
.summary {
  display: flex;
  flex-wrap: wrap;
  gap: 1.5rem;
  margin: 1.5rem 0;
}
.summary div {
  border-left: 1px solid var(--border);
  padding-left: 1rem;
}
.summary strong {
  display: block;
  font-size: 1.2rem;
}
.summary span {
  font-size: .8rem;
  color: var(--muted);
}
button,
.button {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border: 1px solid var(--controlBorder);
  background: white;
  color: var(--ink);
  border-radius: ${t.radius.sm};
  padding: .55rem .85rem;
  cursor: pointer;
  text-decoration: none;
  font-size: .8rem;
  min-height: 2.5rem;
}
button:hover,
.hover-specimen {
  background: var(--canvas);
}
.primary {
  background: var(--accent);
  border-color: var(--accent);
  color: white;
}
.primary:hover {
  background: #1c71d8;
}
.focus-specimen {
  outline: 3px solid var(--focus);
  outline-offset: 3px;
}
button:disabled {
  opacity: .55;
  cursor: not-allowed;
}
.footer {
  margin-top: 3rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border);
  font-size: .75rem;
  color: var(--muted);
}
@media (max-width: 1050px) {
  .layout {
    grid-template-columns: 11rem minmax(0, 1fr);
    gap: 1.5rem;
  }
}
@media (max-width: 700px) {
  .header-inner {
    padding: 1rem;
  }
  .layout {
    display: block;
    padding: 1.5rem 1rem;
  }
  nav {
    position: static;
    display: flex;
    gap: .2rem;
    flex-wrap: wrap;
    margin-bottom: 2rem;
  }
  nav .eyebrow {
    width: 100%;
  }
  nav a {
    padding: .4rem .6rem;
    border-left: 0;
    border-bottom: 2px solid transparent;
    font-size: .85rem;
  }
  .section-heading {
    display: block;
  }
  .section-heading small {
    display: block;
    margin-top: .5rem;
  }
  .badge {
    font-size: .6rem;
  }
  h1 {
    font-size: 2rem;
  }
}
@media (prefers-reduced-motion: reduce) {
  html {
    scroll-behavior: auto;
  }
}
`;
}
