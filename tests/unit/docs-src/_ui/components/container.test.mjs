import { test } from "node:test";
import assert from "node:assert/strict";
import { withComponentPage } from "../../../../helpers/docs-browser.mjs";

test('Container preserves light-DOM content and actual Adapter styling', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (()=>check(`const c=new Components.Container(),p=document.createElement('p'),Adapter=Object.getPrototypeOf(Components.Base);c.append(p,'<literal>');document.body.append(c);const count=document.adoptedStyleSheets.length;c.remove();document.body.append(c);c.css='outline:5px solid rgb(1, 2, 3)';return c instanceof Components.Base&&c instanceof Adapter&&customElements.get('nw-container')===Components.Container&&c.firstChild===p&&c.lastChild.textContent==='<literal>'&&c.shadowRoot===null&&document.adoptedStyleSheets.length===count&&getComputedStyle(c).outlineColor==='rgb(1, 2, 3)'&&getComputedStyle(c).backgroundColor==='rgba(0, 0, 0, 0)';`))();
  });
});

test('Container has a centered 1000px outer cap and fluid padded sizing', { skip: !process.env.DOCS_TEST_CDP }, async () => {
  await withComponentPage(async ({ check, page }) => {
    await (async()=>{
      await check(`const c=new Components.Container(),content=document.createElement('div');content.style.height='20px';c.append(content);document.body.style.margin='0';document.body.replaceChildren(c);return true;`);
      for(const width of [1440,1000,768,390,320]){
        await page.call('Emulation.setDeviceMetricsOverride',{width,height:800,deviceScaleFactor:1,mobile:false});
        await check(`const c=document.querySelector('nw-container'),r=c.getBoundingClientRect(),s=getComputedStyle(c),available=document.documentElement.clientWidth,padding=parseFloat(s.paddingLeft),font=parseFloat(getComputedStyle(document.documentElement).fontSize);const valid=Math.abs(r.width-Math.min(1000,available))<1&&Math.abs(r.left-(available-r.width)/2)<1&&s.boxSizing==='border-box'&&padding>=font-.1&&padding<=2*font+.1&&Math.abs(r.height-20)<.5&&document.documentElement.scrollWidth<=innerWidth;if(!valid)throw Error(JSON.stringify({rect:r.toJSON(),available,viewport:innerWidth,padding,font,boxSizing:s.boxSizing,scrollWidth:document.documentElement.scrollWidth}));return true;`);
      }
    })();
  });
});
