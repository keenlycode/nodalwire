import { test } from "node:test";
import assert from "node:assert/strict";
import { connect } from "../../helpers/docs-browser.mjs";

const routes = ["/", "/getting-started/", "/guides/networks/", "/guides/request-reply/", "/guides/security/", "/reference/api/", "/reference/cli/", "/reference/config/", "/reference/admin/"];

test("product routes preserve native semantics, responsive geometry, contrast and exact code", {
  skip: !process.env.DOCS_TEST_CDP || !process.env.DOCS_TEST_ORIGIN,
}, async () => {
  const owner = await connect(process.env.DOCS_TEST_CDP);
  let page, targetId;
  try {
    ({ targetId } = await owner.call("Target.createTarget", { url: "about:blank", background: true }));
    page = await connect(process.env.DOCS_TEST_CDP.replace(/\/devtools\/.*$/, `/devtools/page/${targetId}`));
    await page.call("Page.enable");
    async function value(expression) {
      const result = await page.call("Runtime.evaluate", { expression: `(async()=>{${expression}})()`, awaitPromise: true, returnByValue: true });
      assert.equal(result.exceptionDetails, undefined, JSON.stringify(result.exceptionDetails));
      return result.result.value;
    }
    async function navigate(route, noJS = false) {
      await page.call("Emulation.setScriptExecutionDisabled", { value: noJS });
      const loaded = new Promise((resolve, reject) => {
        const timeout = setTimeout(() => { page.socket.removeEventListener("message", listener); reject(Error("owned page load deadline")); }, 10000);
        const listener = event => {
          if (JSON.parse(event.data).method === "Page.loadEventFired") {
            clearTimeout(timeout); page.socket.removeEventListener("message", listener); resolve();
          }
        };
        page.socket.addEventListener("message", listener);
      });
      await page.call("Page.navigate", { url: process.env.DOCS_TEST_ORIGIN + route });
      await loaded;
    }
    for (const route of routes) {
      await navigate(route);
      assert.equal(await value(`return document.querySelectorAll('main#main').length===1&&document.querySelectorAll('main > nw-container').length===1&&document.querySelectorAll('h1').length===1&&document.querySelectorAll('nav[aria-label="Documentation"] a[aria-current="page"]').length===1&&document.querySelectorAll('nw-page-path a[aria-current="page"]').length===1;`), true, route);
      for (const width of [1440, 768, 375, 320]) {
        await page.call("Emulation.setDeviceMetricsOverride", { width, height: 1000, deviceScaleFactor: 1, mobile: false });
        assert.equal(await value(`const c=document.querySelector('main > nw-container'),r=c.getBoundingClientRect();return document.documentElement.scrollWidth<=innerWidth&&r.width<=1000&&Math.abs(r.left-(document.documentElement.clientWidth-r.width)/2)<1&&[...document.querySelectorAll('nw-code-block')].every(b=>{const p=b.querySelector('pre'),h=b.querySelector('.code-block-header');return p.clientWidth<=b.clientWidth&&Math.abs(parseFloat(getComputedStyle(p).lineHeight)/parseFloat(getComputedStyle(p).fontSize)-1.5)<0.001&&(!h||h.getBoundingClientRect().bottom<=p.getBoundingClientRect().top+1);});`), true, `${route} width=${width}`);
      }
      assert.equal(await value(`function rgb(s){return s.match(/[\\d.]+/g).slice(0,3).map(Number)}function lum(c){return c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0)}function background(e){for(;e;e=e.parentElement){const c=getComputedStyle(e).backgroundColor;if(c!=='rgba(0, 0, 0, 0)'&&c!=='transparent')return rgb(c)}return [255,255,255]}return [...document.querySelectorAll('h1,.lead,.product-navigation a,.product-navigation h2,.product-footer')].every(e=>{const a=lum(rgb(getComputedStyle(e).color)),b=lum(background(e));return (Math.max(a,b)+.05)/(Math.min(a,b)+.05)>=4.5});`), true, `contrast ${route}`);
      if (route === "/getting-started/") {
        for (const preference of ["light", "dark"]) {
          await page.call("Emulation.setEmulatedMedia", { features: [{ name: "prefers-color-scheme", value: preference }] });
          assert.equal(await value(`function rgb(s){return s.match(/[\\d.]+/g).slice(0,3).map(Number)}function lum(c){return c.map(v=>{v/=255;return v<=.04045?v/12.92:((v+.055)/1.055)**2.4}).reduce((a,v,i)=>a+v*[.2126,.7152,.0722][i],0)}function background(e){for(;e;e=e.parentElement){const c=getComputedStyle(e).backgroundColor;if(c!=='rgba(0, 0, 0, 0)'&&c!=='transparent')return rgb(c)}return [255,255,255]}await customElements.whenDefined('nw-code-block');for(const b of document.querySelectorAll('nw-code-block')){await b.highlight();if(JSON.stringify(background(b))===JSON.stringify(background(document.body)))return false;for(const e of b.querySelectorAll('code,code span,.code-block-labels span')){const a=lum(rgb(getComputedStyle(e).color)),c=lum(background(e));if((Math.max(a,c)+.05)/(Math.min(a,c)+.05)<4.5)return false;}}return true;`), true, `distinct code surface and readable text / ${preference} preference`);
        }
        await page.call("Emulation.setEmulatedMedia", { features: [] });
        assert.equal(await value(`const source=new DOMParser().parseFromString(await(await fetch(location.href)).text(),'text/html');const originals=[...source.querySelectorAll('nw-code-block code')].map(c=>c.textContent);const blocks=[...document.querySelectorAll('nw-code-block')];await customElements.whenDefined('nw-code-block');for(const b of blocks)await b.highlight();const copied=[];Object.defineProperty(navigator,'clipboard',{configurable:true,value:{writeText:async text=>copied.push(text)}});for(let i=0;i<blocks.length;i++){if(blocks[i].code.textContent!==originals[i])return false;blocks[i].querySelector('button').click();await Promise.resolve();if(copied.at(-1)!==originals[i])return false;}return blocks.length>0;`), true, "exact code / clipboard stub only");
        assert.equal(await value(`const fragment=new DOMParser().parseFromString('<code>café 👋&#13;\\nend\\n</code>','text/html');return fragment.querySelector('code').textContent==='café 👋\\r\\nend\\n';`), true, "SSR carriage-return entities preserve CRLF");
      }
    }
    for (const route of ["/", "/getting-started/", "/reference/api/"]) {
      await navigate(route, true);
      assert.equal(await value(`return document.querySelector('main h1').getBoundingClientRect().height>0&&document.querySelectorAll('nav[aria-label="Documentation"] a').length>=9&&[...document.querySelectorAll('nw-code-block')].every(b=>!b.querySelector('button')&&b.querySelector('pre').getBoundingClientRect().height>0&&getComputedStyle(b.querySelector('code')).whiteSpace==='pre'&&getComputedStyle(b).backgroundColor!==getComputedStyle(document.body).backgroundColor)&&document.documentElement.scrollWidth<=innerWidth;`), true, `no-JS ${route}`);
    }
    await page.call("Emulation.setScriptExecutionDisabled", { value: false });
    await navigate("/getting-started/");
    await page.call("Page.bringToFront");
    await page.call("Emulation.setFocusEmulationEnabled", { enabled: true });
    await value(`document.querySelector('.skip').focus();return true;`);
    await page.call("Input.dispatchKeyEvent", { type: "keyDown", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    await page.call("Input.dispatchKeyEvent", { type: "keyUp", key: "Enter", code: "Enter", windowsVirtualKeyCode: 13 });
    assert.equal(await value(`return location.hash==='#main';`), true, "native skip-link Enter activation");
  } finally {
    if (targetId) await owner.call("Target.closeTarget", { targetId });
    page?.socket.close(); owner.socket.close();
  }
});
