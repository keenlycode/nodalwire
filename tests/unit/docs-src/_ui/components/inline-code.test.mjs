import { test } from "node:test";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('InlineCode preserves native code and whitespace', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check }) => check(`const c=Components.InlineCode.create({text:'  <safe> & text\\n  '});document.body.append(c);return c.firstElementChild.tagName==='CODE'&&c.textContent==='  <safe> & text\\n  '&&c.firstElementChild.children.length===0&&getComputedStyle(c.firstElementChild).whiteSpace==='break-spaces';`));
});
test('InlineCode rejects invalid text', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check }) => check(`let errors=0;try{Components.InlineCode.create({text:42})}catch{errors++}return errors===1;`));
});
test('InlineCode Adapter ancestry, shared styling, instance isolation and reconnect', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check }) => check(`const Adapter=Object.getPrototypeOf(Components.Base),C=Components.InlineCode,a=C.create({text:'A'}),b=C.create({text:'A'});document.body.append(a,b);const n=document.adoptedStyleSheets.length;a.css='outline:7px solid rgb(1, 2, 3)';a.remove();document.body.append(a);Components.registerComponents();return a instanceof Adapter&&getComputedStyle(a).boxSizing==='border-box'&&getComputedStyle(a).outlineColor==='rgb(1, 2, 3)'&&getComputedStyle(b).outlineStyle==='none'&&document.adoptedStyleSheets.length===n&&document.adoptedStyleSheets.filter(s=>s===C.adapter.cssStyleSheet).length===1;`));
});
