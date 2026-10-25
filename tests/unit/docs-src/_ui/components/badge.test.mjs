import { test } from "node:test";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('Badge remains static noninteractive safe text', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check }) => check(`const b=Components.Badge.create({text:'<b>Preview</b>'});document.body.append(b);return b.textContent==='<b>Preview</b>'&&!b.querySelector('b')&&b.tabIndex===-1&&!b.hasAttribute('role')&&!b.hasAttribute('tabindex');`));
});
test('Badge rejects invalid text', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check }) => check(`let errors=0;try{Components.Badge.create({text:42})}catch{errors++}try{Components.Badge.create({text:' '})}catch{errors++}return errors===2;`));
});
test('Badge Adapter ancestry, shared styling, instance isolation and reconnect', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check }) => check(`const Adapter=Object.getPrototypeOf(Components.Base),C=Components.Badge,a=C.create({text:'A'}),b=C.create({text:'A'});document.body.append(a,b);const n=document.adoptedStyleSheets.length;a.css='outline:7px solid rgb(1, 2, 3)';a.remove();document.body.append(a);Components.registerComponents();return a instanceof Adapter&&getComputedStyle(a).boxSizing==='border-box'&&getComputedStyle(a).outlineColor==='rgb(1, 2, 3)'&&getComputedStyle(b).outlineStyle==='none'&&document.adoptedStyleSheets.length===n&&document.adoptedStyleSheets.filter(s=>s===C.adapter.cssStyleSheet).length===1;`));
});
