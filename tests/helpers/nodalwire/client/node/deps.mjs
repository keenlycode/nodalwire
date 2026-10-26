import { createRequire } from "node:module";
import { realpathSync } from "node:fs";
import { fileURLToPath } from "node:url";
import path from "node:path";

const packageJson = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  "../../../../../src/nodalwire/client/node/package.json",
);
// Follow the artifact fixture's SDK symlink before resolving native dependencies.
const require = createRequire(realpathSync(packageJson));
export const { Router } = require("zeromq");
