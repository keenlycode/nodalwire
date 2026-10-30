import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('Link factory preserves native URL/text and rejects executable protocols', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const l=Components.Link.create({label:'<img src=x>',href:'../tokens/'});document.body.append(l);let errors=0;for(const o of [{label:'',href:'/'},{label:'x',href:''},{label:'x',href:'javascript:alert(1)'},{label:'x',href:'data:text/html,x'}])try{Components.Link.create(o)}catch{errors++}return errors===4&&l.anchor.getAttribute('href')==='../tokens/'&&l.anchor.href==='https://example.test/design/tokens/'&&l.anchor.textContent==='<img src=x>'&&!l.querySelector('img')&&l.tabIndex===-1&&!l.hasAttribute('role')&&l.anchor.tabIndex===0;`))();
  });
});

test('actual Adapter ancestry, inherited/shared CSS, instance isolation and reconnect', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const Adapter=Object.getPrototypeOf(Components.Base),classes=[Components.Link];for(const C of classes){const options=C===Components.Link?{label:'A',href:'#x'}:{text:'A'};const a=C.create(options),b=C.create(options);document.body.append(a,b);const n=document.adoptedStyleSheets.length;a.css='outline:7px solid rgb(1, 2, 3)';a.remove();document.body.append(a);Components.registerComponents();if(!(a instanceof Adapter)||getComputedStyle(a).boxSizing!=='border-box'||getComputedStyle(a).outlineColor!=='rgb(1, 2, 3)'||getComputedStyle(b).outlineStyle!=='none'||document.adoptedStyleSheets.length!==n||document.adoptedStyleSheets.filter(s=>s===C.adapter.cssStyleSheet).length!==1)return false;}return true;`))();
  });
});

test('authored native anchor remains authoritative across replacement/reconnect', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const host=new Components.Link();const a=document.createElement('a');a.href='#original';a.textContent='Native';a.rel='help';host.append(a);document.body.append(host);host.remove();document.body.append(host);if(host.anchor!==a||a.rel!=='help')return false;const replacement=document.createElement('a');replacement.href='#next';a.replaceWith(replacement);return host.anchor===replacement;`))();
  });
});

test('native Link Tab focus and Enter activation stay on the anchor', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (async()=>{
      await page.call('Page.bringToFront');await page.call('Emulation.setFocusEmulationEnabled',{enabled:true});
      await check(`document.body.replaceChildren();const before=document.createElement('button');before.textContent='Before';window.keyboardLink=Components.Link.create({label:'Keyboard destination',href:'https://example.test/destination'});window.nativeLinkClicks=0;window.nativeLinkTrusted=false;keyboardLink.anchor.addEventListener('click',e=>{e.preventDefault();nativeLinkClicks++;nativeLinkTrusted=e.isTrusted;});document.body.append(before,keyboardLink);before.focus();return keyboardLink.tabIndex===-1;`);
      for(const type of ['rawKeyDown','keyUp'])await page.call('Input.dispatchKeyEvent',{type,key:'Tab',code:'Tab',windowsVirtualKeyCode:9,nativeVirtualKeyCode:9});
      await check(`return document.activeElement===keyboardLink.anchor&&keyboardLink.anchor.matches(':focus-visible')&&getComputedStyle(keyboardLink.anchor).outlineStyle!=='none';`);
      for(const type of ['rawKeyDown','char','keyUp'])await page.call('Input.dispatchKeyEvent',{type,key:'Enter',code:'Enter',windowsVirtualKeyCode:13,nativeVirtualKeyCode:13,...(type==='char'?{text:'\r',unmodifiedText:'\r'}:{})});
      await check(`return nativeLinkClicks===1&&nativeLinkTrusted&&document.activeElement===keyboardLink.anchor;`);
    })();
  });
});
test('Link rejects invalid shape', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check }) => check(`let errors=0;try{new Components.Link().anchor}catch{errors++}return errors===1;`));
});
