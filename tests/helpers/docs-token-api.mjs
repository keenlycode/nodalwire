import { pathToFileURL } from "node:url";
import { root, source, toolRoot, requireDocs } from "./docs.mjs";
const { build } = requireDocs("esbuild");
const bundle = await build({
  stdin: { contents: [
    `export { createTokens, tokens } from ${JSON.stringify(`${source}/_ui/tokens/index.ts`)};`,
    `export { createLift } from ${JSON.stringify(`${source}/_ui/tokens/lift.ts`)};`,
    `export { contrast, reviewData } from ${JSON.stringify(`${toolRoot}/review-data.ts`)};`,
  ].join("\n"), resolveDir: toolRoot, loader: "ts" },
  absWorkingDir: root, bundle: true, platform: "node", format: "esm", write: false,
  nodePaths: [`${toolRoot}/node_modules`],
});
export const api = await import(`data:text/javascript;base64,${Buffer.from(bundle.outputFiles[0].text).toString("base64")}`);
