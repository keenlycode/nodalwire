import { test } from 'node:test';
import assert from 'node:assert/strict';

test('MenuStack actual Adapter and native disclosure behavior', {skip:!process.env.DOCS_TEST_CDP||!process.env.DOCS_TEST_ORIGIN}, async t=>{
  async function connect(url){const socket=new WebSocket(url);await new Promise((r,j)=>{socket.addEventListener('open',r,{once:true});socket.addEventListener('error',j,{once:true});});let id=0;const pending=new Map(),events=new Map();socket.addEventListener('message',e=>{const d=JSON.parse(e.data),p=pending.get(d.id);if(p){pending.delete(d.id);d.error?p.reject(Error(d.error.message)):p.resolve(d.result);}if(d.method&&events.has(d.method)){events.get(d.method)(d.params);events.delete(d.method);}});return {socket,event(name){return new Promise(r=>events.set(name,r));},call(method,params={}){return new Promise((resolve,reject)=>{const n=++id;pending.set(n,{resolve,reject});socket.send(JSON.stringify({id:n,method,params}));});}};}
  const owner=await connect(process.env.DOCS_TEST_CDP);let page,targetId;
  try{
    ({targetId}=await owner.call('Target.createTarget',{url:'about:blank',background:true}));page=await connect(process.env.DOCS_TEST_CDP.replace(/\/devtools\/.*$/,`/devtools/page/${targetId}`));await page.call('Page.enable');
    async function navigate(path,noJS=false){await page.call('Emulation.setScriptExecutionDisabled',{value:noJS});const loaded=page.event('Page.loadEventFired');await page.call('Page.navigate',{url:process.env.DOCS_TEST_ORIGIN+path});await loaded;}
    async function value(code){const r=await page.call('Runtime.evaluate',{expression:`(()=>{${code}})()`,returnByValue:true});assert.equal(r.exceptionDetails,undefined,JSON.stringify(r.exceptionDetails));return r.result.value;}
    async function check(code){assert.equal(await value(code),true);}
    async function key(key,shift=false){const codes={Enter:13,Escape:27,Tab:9,' ':32};for(const type of(key==='Enter'?['rawKeyDown','char','keyUp']:['rawKeyDown','keyUp']))await page.call('Input.dispatchKeyEvent',{type,key,code:key===' '?'Space':key,windowsVirtualKeyCode:codes[key],nativeVirtualKeyCode:codes[key],modifiers:shift?8:0,...(type==='char'?{text:'\r',unmodifiedText:'\r'}:{})});}
    await t.test('official chevron native disclosure and independent parent link, including no-JS',async()=>{
      for(const noJS of [false,true]){
        await navigate('/design/components/',noJS);
        if(!noJS)await check(`document.querySelector('[data-design-navigation] button').click();return !document.querySelector('#design-menu-panel').hidden;`);
        await page.call('Page.bringToFront');await page.call('Emulation.setFocusEmulationEnabled',{enabled:true});
        await check(`const g=document.querySelector('.design-group'),a=g.querySelector(':scope > a'),d=g.querySelector('details'),s=d.querySelector('summary'),icon=s.querySelector('svg');window.toggleGroup=d;window.parentActivated=0;a.addEventListener('click',e=>{e.preventDefault();parentActivated++;});a.focus();return d.open&&a.textContent==='Tokens'&&new URL(a.href).pathname==='/design/tokens/'&&s.getAttribute('aria-label')==='Tokens pages'&&!a.contains(s)&&!s.contains(a)&&icon.getAttribute('aria-hidden')==='true'&&icon.getAttribute('focusable')==='false'&&s.getBoundingClientRect().left>=a.getBoundingClientRect().right-1&&s.getBoundingClientRect().height>=40;`);
        if(noJS){const loaded=page.event('Page.loadEventFired');await key('Enter');await loaded;await check(`const g=document.querySelector('.design-group');window.toggleGroup=g.querySelector('details');window.parentActivated=1;g.querySelector(':scope > a').focus();return location.pathname==='/design/tokens/'&&toggleGroup.open;`);}else{await key('Enter');await check(`return parentActivated===1&&toggleGroup.open;`);}
        await key('Tab');await check(`return document.activeElement===toggleGroup.querySelector('summary');`);
        const native=await page.call('Runtime.evaluate',{expression:'toggleGroup.querySelector("summary")'});
        const tree=await page.call('Accessibility.getPartialAXTree',{objectId:native.result.objectId});
        assert.ok(tree.nodes.some(n=>n.role?.value==='DisclosureTriangle'&&n.name?.value==='Tokens pages'&&n.properties?.some(p=>p.name==='expanded'&&p.value.value===true)));
        await key(' ');await check(`return !toggleGroup.open&&parentActivated===1&&getComputedStyle(toggleGroup.querySelector('.design-group-chevron')).transform==='none';`);
        await key('Enter');await check(`return toggleGroup.open&&parentActivated===1&&getComputedStyle(toggleGroup.querySelector('.design-group-chevron')).transform!=='none';`);
        await key('Tab');await check(`return document.activeElement===toggleGroup.querySelector('a');`);
      }
    });
    await navigate('/design/components/');
    await check(`const C=customElements.get('nw-menu-stack'),Base=Object.getPrototypeOf(C),Adapter=Object.getPrototypeOf(Base);const h=new C();h.innerHTML='<nav aria-label="Test menu"><ul><li><a href="#buttons">Overview</a><details open><summary>Children</summary><ul><li><a href="#cards">Card</a></li></ul></details></li></ul></nav>';document.querySelector('main').append(h);window.menuUnderTest=h;return C.name==='MenuStack'&&h instanceof Adapter&&getComputedStyle(h).boxSizing==='border-box'&&h.querySelector('details').open&&document.adoptedStyleSheets.filter(s=>s===C.adapter.cssStyleSheet).length===1;`);
    await check(`const h=menuUnderTest;h.hidden=true;const hidden=getComputedStyle(h).display==='none'&&h.getBoundingClientRect().height===0;h.hidden=false;return hidden&&getComputedStyle(h).display==='block';`);
    await check(`const h=menuUnderTest,C=h.constructor,n=document.adoptedStyleSheets.length,other=new C();h.css='outline:7px solid rgb(1, 2, 3)';h.remove();document.querySelector('main').append(h);return !other.css&&getComputedStyle(h).outlineColor==='rgb(1, 2, 3)'&&document.adoptedStyleSheets.length===n;`);
    await page.call('Page.bringToFront');await page.call('Emulation.setFocusEmulationEnabled',{enabled:true});
    await check(`menuUnderTest.querySelector('summary').focus();return document.activeElement===menuUnderTest.querySelector('summary');`);
    await key('Enter');await check(`return !menuUnderTest.querySelector('details').open;`);
    await key('Enter');await check(`return menuUnderTest.querySelector('details').open;`);
    for(const [width,height] of [[1440,1050],[390,360]]){
      await page.call('Emulation.setDeviceMetricsOverride',{width,height,deviceScaleFactor:1,mobile:false});
      await check(`const h=menuUnderTest;h.css='';h.querySelector('ul').style.minHeight='2000px';return Math.abs(h.getBoundingClientRect().height-innerHeight)<1&&h.scrollHeight>h.clientHeight&&getComputedStyle(h).overflowY==='auto'&&document.documentElement.scrollWidth<=innerWidth;`);
      await check(`menuUnderTest.style.setProperty('--nw-menu-stack-height','auto');const h=menuUnderTest;return Math.abs(h.getBoundingClientRect().height-2000)<1 || (()=>{throw Error(JSON.stringify({height:h.getBoundingClientRect().height,computed:getComputedStyle(h).height,custom:getComputedStyle(h).getPropertyValue('--nw-menu-stack-height'),ul:h.querySelector('ul').getBoundingClientRect().height,style:h.getAttribute('style')}))})();`);
      await check(`menuUnderTest.style.removeProperty('--nw-menu-stack-height');return true;`);
    }
  }finally{if(targetId)await owner.call('Target.closeTarget',{targetId});page?.socket.close();owner.socket.close();}
});
