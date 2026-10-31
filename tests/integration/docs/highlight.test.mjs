import { test } from "node:test";
import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import { work } from "../../helpers/docs.mjs";
import path from "node:path";

test('Browser graph keeps Shiki lazy and limits grammars to Python/JavaScript without WASM',async()=>{
  const meta=JSON.parse(await readFile(path.join(work,'browser-metafile.json'),'utf8'));
  const inputs=Object.keys(meta.inputs),outputs=Object.entries(meta.outputs);
  assert.deepEqual([...new Set(inputs.filter(p=>/\/langs\/dist\//.test(p)).map(p=>p.split('/').at(-1)))].sort(),['javascript.mjs','python.mjs']);
  assert.ok(inputs.every(p=>!p.includes('engine-oniguruma')&&!p.endsWith('.wasm')&&!p.includes('/themes/')));
  const highlight=outputs.find(([,o])=>o.entryPoint?.endsWith('/code-highlight.ts'))?.[0];assert.ok(highlight);
  const initial=new Set();function visit(path){if(initial.has(path))return;initial.add(path);for(const imp of meta.outputs[path].imports)if(imp.kind!=='dynamic-import'&&!imp.external)visit(imp.path);}
  visit(outputs.find(([,o])=>o.entryPoint==='src/docs-src/design/components/index.ts')[0]);assert.ok(!initial.has(highlight));
})
test('Runtime highlighting on served pages, lazy loading, fallback and responsive header', {skip:!process.env.DOCS_TEST_CDP||!process.env.DOCS_TEST_ORIGIN},async t=>{
  async function connect(url){const socket=new WebSocket(url);await new Promise((r,j)=>{socket.addEventListener('open',r,{once:true});socket.addEventListener('error',j,{once:true});});let id=0;const pending=new Map(),events=new Map();socket.addEventListener('message',e=>{const d=JSON.parse(e.data),p=pending.get(d.id);if(p){pending.delete(d.id);d.error?p.reject(Error(d.error.message)):p.resolve(d.result);}events.get(d.method)?.(d.params);});return {socket,on:(name,fn)=>events.set(name,fn),call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});}};}
  const owner=await connect(process.env.DOCS_TEST_CDP);let page,targetId;const requested=[];
  try{
    ({targetId}=await owner.call('Target.createTarget',{url:'about:blank',background:true}));page=await connect(process.env.DOCS_TEST_CDP.replace(/\/devtools\/.*$/,`/devtools/page/${targetId}`));await page.call('Page.enable');await page.call('Network.enable');await page.call('Network.setCacheDisabled',{cacheDisabled:true});page.on('Network.requestWillBeSent',p=>requested.push(new URL(p.request.url).pathname));
    async function value(code){const r=await page.call('Runtime.evaluate',{expression:`(async()=>{${code}})()`,awaitPromise:true,returnByValue:true});assert.equal(r.exceptionDetails,undefined,JSON.stringify(r.exceptionDetails));return r.result.value;}
    async function check(code){assert.equal(await value(code),true);}
    async function navigate(path,noJS=false){await page.call('Emulation.setScriptExecutionDisabled',{value:noJS});const loaded=new Promise(r=>page.on('Page.loadEventFired',r));await page.call('Page.navigate',{url:process.env.DOCS_TEST_ORIGIN+'/dev'+path});await loaded;}
    await t.test('Pages without a supported code block do not fetch the highlighter',async()=>{
      await navigate('/design/tokens/');assert.ok(!requested.some(p=>p.includes('/code-highlight-')));
    });
    await t.test('Production modules highlight both languages, retain exact text and copy only code',async()=>{
      await navigate('/design/components/code-block/');
      await check(`for(const b of document.querySelectorAll('nw-code-block'))await b.highlight();const source=new DOMParser().parseFromString(await(await fetch(location.href)).text(),'text/html');const copied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>copied.push(text)}});for(const b of document.querySelectorAll('nw-code-block')){if(b.dataset.highlight!=='ready'||b.code.textContent!==source.getElementById(b.id).querySelector('code').textContent||new Set([...b.code.querySelectorAll('span')].map(s=>s.style.color)).size<3)return false;b.querySelector('button').click();await Promise.resolve();if(copied.at(-1)!==b.code.textContent)return false;}return copied.length===2;`);
      for(const kind of ['code-highlight','python','javascript'])assert.equal(requested.filter(p=>p.includes('/'+kind+'-')).length,1);
    });
    await t.test('Header remains above the independently scrolling code on desktop/tablet/mobile',async()=>{
      for(const width of [1440,768,390,320]){
        await page.call('Emulation.setDeviceMetricsOverride',{width,height:1000,deviceScaleFactor:1,mobile:false});
        await check(`return document.documentElement.scrollWidth<=innerWidth&&[...document.querySelectorAll('nw-code-block')].every(b=>{const h=b.querySelector('.code-block-header'),button=b.querySelector('button'),pre=b.querySelector('pre'),labels=b.querySelector('.code-block-labels'),r=button.getBoundingClientRect(),header=h.getBoundingClientRect(),before=labels.getBoundingClientRect().left;pre.scrollLeft=200;return r.right<=header.right&&r.left>=labels.getBoundingClientRect().right&&Math.abs((r.top+r.bottom-header.top-header.bottom)/2)<1&&header.bottom<=pre.getBoundingClientRect().top+1&&labels.getBoundingClientRect().left===before&&pre.scrollWidth>=pre.clientWidth;});`);
      }
    });
    await t.test('No-JS keeps authored filename/language headers and unmodified readable code',async()=>{
      await navigate('/design/components/code-block/',true);
      await check(`return [...document.querySelectorAll('nw-code-block')].every(b=>!b.querySelector('button')&&!b.querySelector('code > span')&&b.querySelector('.code-block-filename').textContent===b.getAttribute('filename')&&b.querySelector('.code-block-language').getBoundingClientRect().height>0&&getComputedStyle(b.querySelector('code')).whiteSpace==='pre')&&document.documentElement.scrollWidth<=innerWidth;`);
    });
    await t.test('Blocked engine download leaves plain text and a functional copy action',async()=>{
      await page.call('Network.setBlockedURLs',{urls:['*/code-highlight-*.js']});await navigate('/design/components/code-block/');
      await check(`const copied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>copied.push(text)}});for(const b of document.querySelectorAll('nw-code-block')){await b.highlight();if(b.dataset.highlight!=='plain'||b.code.querySelector('span')||!b.code.textContent.length)return false;b.querySelector('button').click();await Promise.resolve();if(copied.at(-1)!==b.code.textContent)return false;}return copied.length===2;`);
    });
  }finally{if(targetId)await owner.call('Target.closeTarget',{targetId});page?.socket.close();owner.socket.close();}
})
