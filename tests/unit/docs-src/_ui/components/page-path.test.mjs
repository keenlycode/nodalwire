import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('PagePath preserves caller-owned native navigation and Adapter instance styling', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const p=new Components.PagePath(),nav=document.createElement('nav'),Adapter=Object.getPrototypeOf(Components.Base);nav.setAttribute('aria-label','Example location');nav.innerHTML='<ol><li><a href="#ancestor">Example ancestor</a></li><li><a href="#current" aria-current="page">Example current</a></li></ol>';p.append(nav);document.body.append(p);const count=document.adoptedStyleSheets.length;p.remove();document.body.append(p);p.css='outline:5px solid rgb(1, 2, 3)';return p instanceof Adapter&&p instanceof Components.Base&&p.firstChild===nav&&p.shadowRoot===null&&customElements.get('nw-page-path')===Components.PagePath&&document.adoptedStyleSheets.length===count&&getComputedStyle(p).outlineColor==='rgb(1, 2, 3)'&&getComputedStyle(nav).position==='static'&&getComputedStyle(nav.firstChild).display==='flex'&&nav.querySelectorAll('a').length===2&&nav.querySelectorAll('a[aria-current=page]').length===1;`))();
  });
});
