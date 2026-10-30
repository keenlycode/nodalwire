import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('factory validates names and renders safe deterministic SVG', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`let rejected=0;for(const label of ['', '  ', null, 4])try{Components.IconButton.create({label})}catch{rejected++}const b=Components.IconButton.create({label:'<img onerror=alert(1)>'});document.body.append(b);return rejected===4&&b.button.getAttribute('aria-label')==='<img onerror=alert(1)>'&&b.button.querySelectorAll('svg').length===1&&b.button.querySelector('svg').getAttribute('aria-hidden')==='true'&&!b.querySelector('img,script')&&b instanceof Components.Button&&b.shadowRoot===null;`))();
  });
});
