import assert from "node:assert/strict";
import path from "node:path";
import { pathToFileURL } from "node:url";
import { root, source, toolRoot, work, requireDocs } from "./docs.mjs";

const esbuild = requireDocs("esbuild");
export async function connect(url) {
  const socket = new WebSocket(url);
  await new Promise((resolve, reject) => {
    socket.addEventListener("open", resolve, { once: true });
    socket.addEventListener("error", reject, { once: true });
  });
  let id = 0;
  const pending = new Map();
  socket.addEventListener("message", event => {
    const data = JSON.parse(event.data), item = pending.get(data.id);
    if (!item) return;
    pending.delete(data.id);
    data.error ? item.reject(new Error(data.error.message)) : item.resolve(data.result);
  });
  return { socket, call(method, params = {}) { return new Promise((resolve, reject) => {
    const n = ++id; pending.set(n, { resolve, reject }); socket.send(JSON.stringify({ id: n, method, params }));
  }); } };
}

export async function withComponentPage(run) {
  const owner = await connect(process.env.DOCS_TEST_CDP);
  let page, targetId;
  try {
    ({ targetId } = await owner.call("Target.createTarget", { url: "about:blank", background: true }));
    const pageUrl = process.env.DOCS_TEST_CDP.replace(/\/devtools\/.*$/, `/devtools/page/${targetId}`);
    page = await connect(pageUrl);
    const resolveModule = await import(pathToFileURL(`${work}/resolve.mjs`).href);
    const bundle = await esbuild.build({
      entryPoints: [path.join(source, "_ui/components/index.ts")], bundle: true, write: false,
      format: "iife", globalName: "Components", platform: "browser", absWorkingDir: root,
      nodePaths: [path.join(toolRoot, "node_modules")], resolveExtensions: [".ts", ".js"],
      define: { __NW_COMPONENT_STYLES__: JSON.stringify(resolveModule.default.componentStyles) },
    });
    const result = await page.call("Runtime.evaluate", { expression: bundle.outputFiles[0].text + ";Components.registerComponents();" });
    assert.equal(result.exceptionDetails, undefined, JSON.stringify(result.exceptionDetails));
    await page.call("Runtime.evaluate", { expression: `const base=document.createElement('base');base.href='https://example.test/design/components/';document.head.append(base);` });
    const check = async expression => {
      const result = await page.call("Runtime.evaluate", { expression: `(()=>{${expression}})()`, returnByValue: true });
      assert.equal(result.exceptionDetails, undefined, JSON.stringify(result.exceptionDetails));
      assert.equal(result.result.value, true);
    };
    await run({ page, check, owner });
  } finally {
    if (targetId) await owner.call("Target.closeTarget", { targetId });
    page?.socket.close(); owner.socket.close();
  }
}
