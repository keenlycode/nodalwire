import { test } from "node:test";
import assert from "node:assert/strict";
import { requireDocs, source, toolRoot, root } from "../../../../helpers/docs.mjs";
import path from "node:path";
const { build } = requireDocs("esbuild");

const compiled = await build({ stdin: { contents: `export * from ${JSON.stringify(path.join(source, "_ui/components/code-highlight.ts"))};\nexport { contrast } from ${JSON.stringify(path.join(toolRoot, "review-data.ts"))};`, resolveDir: toolRoot, loader: "ts" }, absWorkingDir: root, bundle: true, write: false, format: "esm", platform: "node", nodePaths: [path.join(toolRoot, "node_modules")] });
const api = await import(`data:text/javascript;base64,${Buffer.from(compiled.outputFiles[0].text).toString("base64")}`);

test('Syntax theme uses readable normal-text contrast',()=>{
  const bg=api.syntaxTheme.colors['editor.background'];
  for(const fg of [api.syntaxTheme.colors['editor.foreground'],...api.syntaxTheme.tokenColors.map(t=>t.settings.foreground)])assert.ok(api.contrast(fg,bg)>=4.5,`${fg} against ${bg}`);
})
test('Token offsets preserve separators, Unicode and empty/final lines',async()=>{
  for(const language of ['python','javascript'])for(const text of ['', '\n', 'value = "👋 <tag> & text"\r\n\t# end\r\n\r\n', 'a = 1\rb = 2\n']){
    const tokens=await api.tokenizeCode(text,language);let restored='',cursor=0;
    for(const token of tokens){assert.ok(token.offset>=cursor);restored+=text.slice(cursor,token.offset)+token.content;cursor=token.offset+token.content.length;}
    assert.equal(restored+text.slice(cursor),text);
  }
})
