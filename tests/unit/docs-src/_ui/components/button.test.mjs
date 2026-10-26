import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('real Adapter ancestry, inherited CSS, shared sheets and isolated instance CSS', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const B=Components.Button,C=Components.Card,Base=Components.Base,Adapter=Object.getPrototypeOf(Base);const a=B.create({label:'A'}),b=B.create({label:'B'}),c=C.create();document.body.append(a,b,c);const count=document.adoptedStyleSheets.length;Components.registerComponents();a.remove();document.body.append(a);a.css='outline:7px solid rgb(1, 2, 3)';const checks={ancestry:a instanceof Adapter&&c instanceof Adapter,controller:B.adapter!==C.adapter,sheetCount:document.adoptedStyleSheets.length===count,shared:document.adoptedStyleSheets.filter(s=>s===B.adapter.cssStyleSheet).length===1,buttonBase:getComputedStyle(a).boxSizing==='border-box',cardBase:getComputedStyle(c).boxSizing==='border-box',font:getComputedStyle(a).fontFamily===getComputedStyle(c).fontFamily,instance:getComputedStyle(a).outlineColor==='rgb(1, 2, 3)'&&parseFloat(getComputedStyle(a).outlineWidth)>5,isolation:getComputedStyle(b).outlineStyle==='none',card:getComputedStyle(c).display==='grid',native:getComputedStyle(a.button).minHeight==='36px'};if(!Object.values(checks).every(Boolean))throw Error(JSON.stringify({checks,outline:getComputedStyle(a).outline,css:a.css,html:a.outerHTML,attached:document.adoptedStyleSheets.includes(a._adapter.cssStyleSheet)}));return true;`))();
  });
});

test('factories preserve safe text, type, disabled and native identity', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const b=Components.Button.create({label:'<b>Text</b>',type:'submit',disabled:true});document.body.append(b);return b.button.textContent==='<b>Text</b>'&&b.button.children.length===0&&b.button.type==='submit'&&b.button.disabled&&b.shadowRoot===null;`))();
  });
});

test('factories reject invalid inputs and malformed direct-child shape', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`let n=0;for(const d of [{label:''},{label:'x',type:'wrong'},{label:'x',disabled:'false'}])try{Components.Button.create(d)}catch{n++}const b=new Components.Button();try{b.button}catch{n++}b.append(document.createElement('button'),document.createElement('button'));try{b.button}catch{n++}return n===5;`))();
  });
});

test('authored attributes, content and replacement stay authoritative', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const b=new Components.Button();b.innerHTML='<button type="reset" name="native" disabled="false">Authored</button>';document.body.append(b);const old=b.button;b.remove();document.body.append(b);if(b.button!==old||!old.disabled||old.type!=='reset'||old.textContent!=='Authored')return false;const next=document.createElement('button');old.replaceWith(next);return b.button===next;`))();
  });
});

test('native submitter/reset/disabled semantics remain intact', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const f=document.createElement('form');f.innerHTML='<input name="draft" value="Draft">';const submit=Components.Button.create({label:'Submit',type:'submit'}),reset=Components.Button.create({label:'Reset',type:'reset'});submit.button.name='intent';submit.button.value='review';f.append(submit,reset);document.body.append(f);let valid=false;f.addEventListener('submit',e=>{e.preventDefault();valid=e.submitter===submit.button&&new FormData(f).get('draft')==='Changed'});f.elements.draft.value='Changed';submit.button.click();reset.button.click();let clicked=false;submit.button.addEventListener('click',()=>clicked=true);submit.button.disabled=true;submit.button.click();return valid&&f.elements.draft.value==='Draft'&&!clicked&&submit.button.form===f;`))();
  });
});
