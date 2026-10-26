import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('Card preserves nodes, text safety and light DOM', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const node=document.createElement('p');const c=Components.Card.create({children:[node,'<safe>']});return c.firstChild===node&&c.lastChild.textContent==='<safe>'&&c.shadowRoot===null;`))();
  });
});
