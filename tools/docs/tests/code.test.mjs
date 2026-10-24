import { test } from 'node:test';
import assert from 'node:assert/strict';
import { build } from 'esbuild';

test('IconButton/CodeBlock owned-browser contracts (clipboard stub ONLY)', {skip: !process.env.DOCS_TEST_CDP || !process.env.DOCS_TEST_ORIGIN}, async t => {
  async function connect(url) {
    const socket=new WebSocket(url); await new Promise((resolve,reject)=>{socket.addEventListener('open',resolve,{once:true});socket.addEventListener('error',reject,{once:true});});
    let id=0;const pending=new Map();socket.addEventListener('message',e=>{const d=JSON.parse(e.data),p=pending.get(d.id);if(p){pending.delete(d.id);d.error?p.reject(Error(d.error.message)):p.resolve(d.result);}});
    return {socket,call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});}};
  }
  const owner=await connect(process.env.DOCS_TEST_CDP);let page,targetId;
  try {
    ({targetId}=await owner.call('Target.createTarget',{url:'about:blank',background:true}));
    page=await connect(process.env.DOCS_TEST_CDP.replace(/\/devtools\/.*$/,`/devtools/page/${targetId}`));
    // Navigate to loopback with no runtime admission; target owns its clipboard stub.
    await page.call('Page.enable');
    await page.call('Page.navigate',{url:process.env.DOCS_TEST_ORIGIN+'/assets/licenses/gnomicon/NOTICE.md'});
    async function run(code){const r=await page.call('Runtime.evaluate',{expression:`(async()=>{${code}})()`,awaitPromise:true,returnByValue:true});assert.equal(r.exceptionDetails,undefined,JSON.stringify(r.exceptionDetails));return r.result.value;}
    await run(`await new Promise(r=>document.readyState==='complete'?r():window.addEventListener('load',r,{once:true}));return true;`);
    const {default:data}=await import('../.build/resolve.mjs');
    const bundle=await build({entryPoints:['../../docs-src/_ui/components/index.ts'],bundle:true,write:false,format:'iife',globalName:'Components',platform:'browser',nodePaths:['./node_modules'],define:{__NW_COMPONENT_STYLES__:JSON.stringify(data.componentStyles)}});
    const bootstrap=await page.call('Runtime.evaluate',{expression:bundle.outputFiles[0].text+';Components.registerComponents();document.body.replaceChildren();'});
    assert.equal(bootstrap.exceptionDetails,undefined,JSON.stringify(bootstrap.exceptionDetails));
    async function check(code){assert.equal(await run(code),true);}
    await t.test('factory validates names and renders safe deterministic SVG',()=>check(`let rejected=0;for(const label of ['', '  ', null, 4])try{Components.IconButton.create({label})}catch{rejected++}const b=Components.IconButton.create({label:'<img onerror=alert(1)>'});document.body.append(b);return rejected===4&&b.button.getAttribute('aria-label')==='<img onerror=alert(1)>'&&b.button.querySelectorAll('svg').length===1&&b.button.querySelector('svg').getAttribute('aria-hidden')==='true'&&!b.querySelector('img,script')&&b instanceof Components.Button&&b.shadowRoot===null;`));
    await t.test('actual Adapter class and instance CSS with reconnect isolation',()=>check(`const a=Components.IconButton.create({label:'A'}),b=Components.IconButton.create({label:'B'}),c=Components.CodeBlock.create({text:'x'});document.body.append(a,b,c);a.css='outline:7px solid rgb(1, 2, 3)';c.css='outline:5px solid rgb(3, 2, 1)';const n=document.adoptedStyleSheets.length;c.remove();document.body.append(c);Components.registerComponents();return a instanceof Object.getPrototypeOf(Components.Base)&&c instanceof Components.Base&&Math.abs(parseFloat(getComputedStyle(a.button).width)-2.25*parseFloat(getComputedStyle(document.documentElement).fontSize))<.1&&getComputedStyle(a).outlineColor==='rgb(1, 2, 3)'&&getComputedStyle(b).outlineStyle==='none'&&parseFloat(getComputedStyle(c).outlineWidth)>4&&document.adoptedStyleSheets.length===n&&c.querySelectorAll('nw-icon-button').length===1 || (()=>{throw Error(JSON.stringify({width:getComputedStyle(a.button).width,outline:getComputedStyle(a).outline,other:getComputedStyle(b).outline,code:getComputedStyle(c).outline,sheets:document.adoptedStyleSheets.length,n,actions:c.querySelectorAll('nw-icon-button').length}))})();`));
    await t.test('code is exact safe text with whitespace and no HTML interpretation',()=>check(`window.payload='  <img src=x onerror=alert(1)> &\\n\\tsecond line\\n';window.block=Components.CodeBlock.create({text:payload});document.body.append(block);return block.code.textContent===payload&&!block.querySelector('img')&&block.querySelector('pre').tabIndex===0&&getComputedStyle(block.code).whiteSpace==='pre';`));
    await t.test('stub success exact payload and accessible status without focus theft',()=>check(`window.calls=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>{calls.push(text)}}});block.querySelector('button').focus();block.querySelector('button').click();await Promise.resolve();const s=block.querySelector('output');return calls.length===1&&calls[0]===payload&&s.textContent==='Code copied.'&&s.getAttribute('role')==='status'&&s.getAttribute('aria-live')==='polite'&&document.activeElement===block.querySelector('button');`));
    await t.test('denied and unsupported clipboard report truthful failure',()=>check(`Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async()=>{throw Error('denied')}}});block.querySelector('button').click();await Promise.resolve();const denied=block.querySelector('output').textContent.includes('Could not copy');Object.defineProperty(navigator,'clipboard',{configurable:true,value:undefined});block.querySelector('button').click();await Promise.resolve();return denied&&block.querySelector('output').textContent.includes('manually');`));
    await t.test('pending guard and reconnect do not duplicate requests/listeners',()=>check(`window.count=0;window.finish=null;Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:()=>{count++;return new Promise(r=>finish=r)}}});const b=block.querySelector('button');b.click();b.click();block.remove();document.body.append(block);b.click();const guarded=count===1&&block.querySelector('output').textContent==='Copying…'&&block.querySelectorAll('button').length===1;finish();await Promise.resolve();b.click();const again=count===2;finish();await Promise.resolve();return guarded&&again;`));
    await t.test('native Enter/Space activate stubbed copy; disabled skips activation',async()=>{
      await page.call('Page.bringToFront');
      await page.call('Emulation.setFocusEmulationEnabled',{enabled:true});
      await run(`block.querySelector('pre').focus();return true;`);
      for(const type of ['rawKeyDown','keyUp'])await page.call('Input.dispatchKeyEvent',{type,key:'Tab',code:'Tab',windowsVirtualKeyCode:9,nativeVirtualKeyCode:9});
      await check(`return document.activeElement===block.querySelector('button');`);
      for(const type of ['rawKeyDown','keyUp'])await page.call('Input.dispatchKeyEvent',{type,key:'Tab',code:'Tab',windowsVirtualKeyCode:9,nativeVirtualKeyCode:9,modifiers:8});
      await check(`return document.activeElement===block.querySelector('pre');`);
      await run(`window.keys=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>keys.push(text)}});block.querySelector('button').focus();return true;`);
      for(const key of ['Enter',' ']){for(const type of (key==='Enter'?['rawKeyDown','char','keyUp']:['rawKeyDown','keyUp']))await page.call('Input.dispatchKeyEvent',{type,key,code:key==='Enter'?'Enter':'Space',windowsVirtualKeyCode:key==='Enter'?13:32,nativeVirtualKeyCode:key==='Enter'?13:32,...(type==='char'?{text:'\r',unmodifiedText:'\r'}:{})});}
      assert.deepEqual(await run(`return {count:keys.length,exact:keys.every(x=>x===payload),focus:document.activeElement===block.querySelector('button'),visible:document.activeElement.matches(':focus-visible')};`),{count:2,exact:true,focus:true,visible:true});
      await check(`const b=block.querySelector('button');b.disabled=true;b.click();const disabled=Components.IconButton.create({label:'Disabled icon',disabled:true});window.afterDisabled=document.createElement('button');afterDisabled.textContent='After disabled';document.body.append(disabled,afterDisabled);block.querySelector('pre').focus();return keys.length===2;`);
      for(const type of ['rawKeyDown','keyUp'])await page.call('Input.dispatchKeyEvent',{type,key:'Tab',code:'Tab',windowsVirtualKeyCode:9,nativeVirtualKeyCode:9});
      await check(`return document.activeElement===afterDisabled&&keys.length===2;`);
    });
  } finally {if(targetId)await owner.call('Target.closeTarget',{targetId});page?.socket.close();owner.socket.close();}
});
