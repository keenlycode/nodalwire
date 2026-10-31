import { test } from "node:test";
import assert from "node:assert/strict";

const enabled = Boolean(process.env.DOCS_TEST_CDP && process.env.DOCS_TEST_ORIGIN);

test("Message diagrams in an explicitly owned browser target", { skip: !enabled }, async t => {
  async function connect(url) {
    const socket = new WebSocket(url);
    await new Promise((resolve, reject) => {
      socket.addEventListener("open", resolve, { once: true });
      socket.addEventListener("error", reject, { once: true });
    });
    let id = 0; const pending = new Map();
    socket.addEventListener("message", event => {
      const message = JSON.parse(event.data), entry = pending.get(message.id);
      if (!entry) return;
      pending.delete(message.id); clearTimeout(entry.timer);
      message.error ? entry.reject(Error(message.error.message)) : entry.resolve(message.result);
    });
    return {
      socket,
      once(method) {
        return new Promise((resolve, reject) => {
          const listener = event => {
            const message = JSON.parse(event.data);
            if (message.method !== method) return;
            clearTimeout(timer); socket.removeEventListener("message", listener);
            resolve(message.params);
          };
          const timer = setTimeout(() => {
            socket.removeEventListener("message", listener);
            reject(Error(`CDP event timeout: ${method}`));
          }, 15000);
          socket.addEventListener("message", listener);
        });
      },
      call(method, params = {}) {
        return new Promise((resolve, reject) => {
          const current = ++id;
          const timer = setTimeout(() => { pending.delete(current); reject(Error(`CDP timeout: ${method}`)); }, 15000);
          pending.set(current, { resolve, reject, timer });
          socket.send(JSON.stringify({ id: current, method, params }));
        });
      },
    };
  }
  const owner = await connect(process.env.DOCS_TEST_CDP);
  let targetId, page;
  try {
    ({ targetId } = await owner.call("Target.createTarget", { url: "about:blank", background: true }));
    page = await connect(process.env.DOCS_TEST_CDP.replace(/\/devtools\/.*$/, `/devtools/page/${targetId}`));
    await page.call("Page.enable");
    // The whole-site runner supplies an origin; focused runs may supply /dev/
    // (or a release-version prefix). Do not navigate to root /messaging/.
    const base = new URL(process.env.DOCS_TEST_ORIGIN);
    base.pathname = base.pathname === "/" ? "/dev/" : base.pathname.replace(/\/$/, "") + "/";
    const url = base.href;
    async function navigate(destination = url) {
      // Subscribe before navigation; do not await a page-side load Promise when
      // script execution is disabled or the execution context is being replaced.
      const loaded = page.once("Page.loadEventFired");
      await page.call("Page.navigate", { url: destination });
      await loaded;
    }
    async function run(code, synchronous = false) {
      const result = await page.call("Runtime.evaluate", { expression: `(${synchronous ? "" : "async "}()=>{${code}})()`, awaitPromise: !synchronous, returnByValue: true });
      assert.equal(result.exceptionDetails, undefined, JSON.stringify(result.exceptionDetails));
      return result.result.value;
    }
    await t.test("actual authored explanation is readable with JavaScript disabled", async () => {
      await page.call("Emulation.setScriptExecutionDisabled", { value: true });
      await navigate();
      const result = await run(`const diagrams=[...document.querySelectorAll('nw-message-diagram')];return {count:diagrams.length,undefined:!customElements.get('nw-message-diagram'),readable:diagrams.every(d=>{const f=d.querySelector('figure'),s=f?.querySelector('ol,p');return f?.querySelector('figcaption')?.textContent.trim()&&s?.textContent.trim()&&s.getBoundingClientRect().height>0;})};`, true);
      assert.ok(result.count > 0, "built landing page should include an authored architecture figure");
      assert.equal(result.undefined, true); assert.equal(result.readable, true);
    });
    await page.call("Emulation.setScriptExecutionDisabled", { value: false });
    await t.test("fresh authored Overview and Messaging enhance without host mutation", async () => {
      await page.call("Emulation.setDeviceMetricsOverride", { width: 375, height: 1000, deviceScaleFactor: 1, mobile: false });
      for (const [route, kinds] of [["", ["architecture"]], ["messaging/", ["send", "request-reply"]]]) {
        await navigate(url + route);
        const result = await run(`await Promise.race([customElements.whenDefined('nw-message-diagram'),new Promise((_,reject)=>setTimeout(()=>reject(Error('authored diagram registration timeout at '+location.href)),8000))]);const expected=${JSON.stringify(kinds)},end=performance.now()+8000;while(expected.some(kind=>document.querySelector('nw-message-diagram[kind="'+kind+'"]')?.dataset.diagramState!=='ready')){if(performance.now()>end)throw Error('Authored first-load enhancement timeout: '+JSON.stringify([...document.querySelectorAll('nw-message-diagram')].map(d=>({kind:d.getAttribute('kind'),state:d.dataset.diagramState,width:d.clientWidth}))));await new Promise(r=>setTimeout(r,25));}return expected.every(kind=>{const d=document.querySelector('nw-message-diagram[kind="'+kind+'"]');return !!d.querySelector('svg')&&d.querySelector('figure > ol').getBoundingClientRect().height>0;});`);
        assert.equal(result, true, route || "Overview");
      }
    });
    await navigate();
    await run(`await Promise.race([customElements.whenDefined('nw-message-diagram'),new Promise((_,reject)=>setTimeout(()=>reject(Error('diagram registration timeout')),8000))]);document.body.replaceChildren();document.body.style.margin='0';window.fixture=document.createElement('div');fixture.style.cssText='width:100%;max-width:900px;margin:auto';document.body.append(fixture);window.makeDiagram=(kind)=>{const host=document.createElement('nw-message-diagram');host.setAttribute('kind',kind);const figure=document.createElement('figure'),caption=document.createElement('figcaption'),steps=document.createElement('ol'),item=document.createElement('li');caption.textContent='Fixture '+kind;item.textContent='Native explanation: queue acceptance is not application processing. Reply uses a fresh ID and reply_to.';steps.append(item);figure.append(caption,steps);host.append(figure);return host;};window.waitFor=async(test)=>{const end=performance.now()+8000;while(!test()){if(performance.now()>end)throw Error('diagram state timeout');await new Promise(r=>setTimeout(r,25));}};return true;`);

    await t.test("all kinds render JointJS SVG and preserve visible accessible native text", async () => {
      for (const kind of ["architecture", "send", "request-reply"]) {
        const result = await run(`fixture.replaceChildren();const d=makeDiagram(${JSON.stringify(kind)}),f=d.querySelector('figure'),steps=f.querySelector('ol'),before=steps.textContent;fixture.append(d);await waitFor(()=>d.dataset.diagramState==='ready'||d.dataset.diagramState==='fallback');return {state:d.dataset.diagramState,svg:!!d.querySelector('svg'),nodes:d.querySelectorAll('[data-diagram-node]').length,hidden:d.querySelector('.message-diagram-visual')?.getAttribute('aria-hidden'),text:steps.textContent===before&&steps.getBoundingClientRect().height>0,owned:f===d.querySelector('figure'),focus:d.querySelectorAll('.message-diagram-visual [tabindex="0"],.message-diagram-visual button').length};`);
        assert.equal(result.state, "ready", kind); assert.equal(result.svg, true); assert.ok(result.nodes >= 4);
        assert.equal(result.hidden, "true"); assert.equal(result.text, true); assert.equal(result.owned, true); assert.equal(result.focus, 0);
      }
    });
    await t.test("compact and wide diagrams keep queues inside relay without canvas overflow", async () => {
      for (const width of [320, 375, 1024]) {
        await page.call("Emulation.setDeviceMetricsOverride", { width, height: 1000, deviceScaleFactor: 1, mobile: false });
        for (const kind of ["architecture", "send", "request-reply"]) {
          const result = await run(`fixture.replaceChildren();const d=makeDiagram(${JSON.stringify(kind)});fixture.append(d);await waitFor(()=>d.dataset.diagramState==='ready');const visual=d.querySelector('.message-diagram-visual'),relay=d.querySelector('[data-diagram-node="relay"] rect').getBoundingClientRect(),queues=[...d.querySelectorAll('[data-node-role="native-queue"] rect')].map(e=>e.getBoundingClientRect()),svg=visual.querySelector('svg').getBoundingClientRect(),box=fixture.getBoundingClientRect();return {layout:visual.dataset.layout,contained:queues.every(q=>q.left>=relay.left-1&&q.right<=relay.right+1&&q.top>=relay.top-1&&q.bottom<=relay.bottom+1),fits:svg.width<=box.width+1&&svg.left>=box.left-1&&svg.right<=box.right+1,clippedLabels:[...visual.querySelectorAll('text')].filter(e=>{const b=e.getBoundingClientRect();return b.left<svg.left-1||b.right>svg.right+1||b.top<svg.top-1||b.bottom>svg.bottom+1;}).map(e=>e.textContent),replyDeliverySeparated:(()=>{if(d.getAttribute('kind')!=='request-reply')return true;const texts=[...visual.querySelectorAll('text')],reply=texts.find(e=>e.textContent.startsWith('3. Reply')),delivery=texts.find(e=>e.textContent.startsWith('2. Receive later;'));if(!reply||!delivery)return false;const a=reply.getBoundingClientRect(),b=delivery.getBoundingClientRect();return a.right+4<=b.left||b.right+4<=a.left||a.bottom+4<=b.top||b.bottom+4<=a.top;})(),font:Math.min(...[...visual.querySelectorAll('text')].map(e=>parseFloat(getComputedStyle(e).fontSize)))};`);
          assert.equal(result.layout, width < 680 ? "compact" : "wide"); assert.equal(result.contained, true); assert.equal(result.fits, true); assert.deepEqual(result.clippedLabels, [], `${kind}/${width}: SVG label extents`); assert.equal(result.replyDeliverySeparated, true, `${kind}/${width}: reply and delivery labels need 4px separation`); assert.ok(result.font >= 13);
        }
      }
    });
    await t.test("kind changes and normal reconnect keep exactly one owned paper", async () => {
      const result = await run(`fixture.replaceChildren();const d=makeDiagram('send');fixture.append(d);await waitFor(()=>d.dataset.diagramState==='ready');const steps=d.querySelector('ol');d.remove();const cleaned=!d.querySelector('.message-diagram-visual');fixture.append(d);await waitFor(()=>d.dataset.diagramState==='ready');d.setAttribute('kind','request-reply');await waitFor(()=>d.dataset.diagramState==='ready');const reply=d.querySelectorAll('[data-diagram-node="reply-queue"]').length;d.setAttribute('kind','unsupported');return {cleaned,reply,fallback:d.dataset.diagramState==='fallback',papers:d.querySelectorAll('svg').length,text:steps===d.querySelector('ol')&&steps.getBoundingClientRect().height>0};`);
      assert.deepEqual(result, { cleaned: true, reply: 1, fallback: true, papers: 0, text: true });
    });
    await t.test("SVG rendering failure leaves the original explanation readable", async () => {
      const result = await run(`fixture.replaceChildren();const d=makeDiagram('send'),steps=d.querySelector('ol'),original=document.createElementNS;let failed=false;try{document.createElementNS=function(ns,...args){if(ns==='http://www.w3.org/2000/svg'){failed=true;throw Error('Owned test: SVG unavailable');}return original.call(this,ns,...args);};fixture.append(d);await waitFor(()=>d.dataset.diagramState==='fallback');}finally{document.createElementNS=original;}return {failed,state:d.dataset.diagramState,svg:!!d.querySelector('svg'),text:steps===d.querySelector('ol')&&steps.getBoundingClientRect().height>0};`);
      assert.deepEqual(result, { failed: true, state: "fallback", svg: false, text: true });
    });
  } finally {
    if (targetId) await owner.call("Target.closeTarget", { targetId });
    page?.socket.close(); owner.socket.close();
  }
});
