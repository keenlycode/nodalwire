import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('Base supplies shared inheritance and safe idempotent registration', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`Components.registerComponents();class Probe extends Components.Base{};Probe.define('nw-base-probe');Probe.define('nw-base-probe');const p=document.createElement('nw-base-probe'),b=Components.Button.create({label:'Base'}),c=Components.Card.create();class Foreign extends HTMLElement{};customElements.define('nw-foreign-probe',Foreign);let guarded=false;try{Probe.define('nw-foreign-probe')}catch{guarded=true}return p instanceof Probe&&p instanceof Components.Base&&b instanceof Components.Base&&c instanceof Components.Base&&customElements.get('nw-button')===Components.Button&&customElements.get('nw-card')===Components.Card&&guarded&&customElements.get('nw-foreign-probe')===Foreign;`))();
  });
});
