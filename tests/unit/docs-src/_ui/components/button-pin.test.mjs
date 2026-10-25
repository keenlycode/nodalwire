import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('ButtonPin preserves native Button API and the approved circle', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const p=Components.ButtonPin.create({label:'Menu'});p.button.setAttribute('aria-label','Open design menu');document.body.append(p);const rect=p.button.getBoundingClientRect(),css=getComputedStyle(p.button);let clicks=0;p.button.addEventListener('click',()=>clicks++);p.button.click();p.button.disabled=true;p.button.click();return p instanceof Components.ButtonPin&&p instanceof Components.Button&&p instanceof Components.Base&&p.button.type==='button'&&p.button.textContent==='Menu'&&p.button.getAttribute('aria-label')==='Open design menu'&&Math.abs(rect.width-rect.height)<1&&css.borderRadius==='50%'&&css.paddingTop==='0px'&&clicks===1&&p.shadowRoot===null;`))();
  });
});
