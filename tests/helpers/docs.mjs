import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { createRequire } from "node:module";

export const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "../..");
export const source = path.join(root, "src/docs-src");
export const toolRoot = path.join(root, "src/tools/docs");
export const work = path.join(toolRoot, ".build");
export const requireDocs = createRequire(pathToFileURL(path.join(toolRoot, "package.json")));
export const docsPath = (...parts) => path.join(toolRoot, ...parts);
