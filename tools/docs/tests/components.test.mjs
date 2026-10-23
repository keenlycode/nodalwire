import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

// Real browser DOM coverage using the already-owned Chrome, no DOM shim/dependency.
test('Button/Card real-browser regression', { skip: !process.env.DOCS_TEST_CDP }, async t => {
  async function connect(url) {
    const socket = new WebSocket(url); await new Promise((resolve,reject) => { socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true}); });
    let id=0; const pending=new Map();
    socket.addEventListener('message',event=>{const data=JSON.parse(event.data);const p=pending.get(data.id);if(p){pending.delete(data.id);data.error?p.reject(new Error(data.error.message)):p.resolve(data.result);}});
    return { socket, call(method,params={}) { return new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));}); } };
  }
  const owner=await connect(process.env.DOCS_TEST_CDP);let page,targetId;
  try {
    ({targetId}=await owner.call('Target.createTarget',{url:'about:blank',background:true}));
    page=await connect(process.env.DOCS_TEST_CDP.replace(/\/devtools\/.*$/,`/devtools/page/${targetId}`));
    const bundle=await build({entryPoints:['../../docs-src/_ui/components/index.ts'],bundle:true,write:false,format:'iife',globalName:'Components',platform:'browser'});
    await page.call('Runtime.evaluate',{expression:bundle.outputFiles[0].text+';Components.registerComponents();'});
    async function check(expression){const r=await page.call('Runtime.evaluate',{expression:`(()=>{${expression}})()`,returnByValue:true});assert.equal(r.exceptionDetails,undefined,JSON.stringify(r.exceptionDetails));assert.equal(r.result.value,true);}
    await t.test('factories preserve safe text, type, disabled and native identity',()=>check(`const b=Components.Button.create({label:'<b>Text</b>',type:'submit',disabled:true});document.body.append(b);return b.button.textContent==='<b>Text</b>'&&b.button.children.length===0&&b.button.type==='submit'&&b.button.disabled&&b.shadowRoot===null;`));
    await t.test('factories reject invalid inputs and malformed direct-child shape',()=>check(`let n=0;for(const d of [{label:''},{label:'x',type:'wrong'},{label:'x',disabled:'false'}])try{Components.Button.create(d)}catch{n++}const b=new Components.Button();try{b.button}catch{n++}b.append(document.createElement('button'),document.createElement('button'));try{b.button}catch{n++}return n===5;`));
    await t.test('authored attributes, content and replacement stay authoritative',()=>check(`const b=new Components.Button();b.innerHTML='<button type="reset" name="native" disabled="false">Authored</button>';document.body.append(b);const old=b.button;b.remove();document.body.append(b);if(b.button!==old||!old.disabled||old.type!=='reset'||old.textContent!=='Authored')return false;const next=document.createElement('button');old.replaceWith(next);return b.button===next;`));
    await t.test('Card preserves nodes, text safety and light DOM',()=>check(`const node=document.createElement('p');const c=Components.Card.create({children:[node,'<safe>']});return c.firstChild===node&&c.lastChild.textContent==='<safe>'&&c.shadowRoot===null;`));
    await t.test('native submitter/reset/disabled semantics remain intact',()=>check(`const f=document.createElement('form');f.innerHTML='<input name="draft" value="Draft">';const submit=Components.Button.create({label:'Submit',type:'submit'}),reset=Components.Button.create({label:'Reset',type:'reset'});submit.button.name='intent';submit.button.value='review';f.append(submit,reset);document.body.append(f);let valid=false;f.addEventListener('submit',e=>{e.preventDefault();valid=e.submitter===submit.button&&new FormData(f).get('draft')==='Changed'});f.elements.draft.value='Changed';submit.button.click();reset.button.click();let clicked=false;submit.button.addEventListener('click',()=>clicked=true);submit.button.disabled=true;submit.button.click();return valid&&f.elements.draft.value==='Draft'&&!clicked&&submit.button.form===f;`));
  } finally {
    if(targetId)await owner.call('Target.closeTarget',{targetId});
    page?.socket.close();owner.socket.close();
  }
});
