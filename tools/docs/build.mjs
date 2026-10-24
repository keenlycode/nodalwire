import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { mkdir, readdir, rm, writeFile, lstat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const toolRoot = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(toolRoot, "../..");
const source = path.join(root, "docs-src");
const work = path.join(toolRoot, ".build");

async function files(directory) {
  const result = [];
  for (const item of await readdir(directory, { withFileTypes: true })) {
    const full = path.join(directory, item.name);
    if (item.isSymbolicLink()) throw new Error(`Symlinks are not documentation inputs: ${full}`);
    if (item.isDirectory()) result.push(...await files(full));
    else if (item.isFile()) result.push(full);
  }
  return result.sort();
}

/** A fresh checkout needs only the pinned tools, not the prototype kernel. */
export async function buildSite() {
  await mkdir(work, { recursive: true });
  const inputs = await files(source);
  const styles = inputs.filter((name) => path.basename(name) === "style.ts");
  const resolveFile = path.join(work, "resolve.mjs");
  const imports = styles.map((name, index) => `import style${index} from ${JSON.stringify(name)};`);
  const styleEntries = styles.map((name, index) => {
    const relative = path.relative(source, name).split(path.sep).join("/").replace(/\.ts$/, ".css");
    return `${JSON.stringify(`assets/${relative}`)}: style${index}(tokens)`;
  });
  await build({
    absWorkingDir: root,
    stdin: {
      contents: [
        `import { tokens } from ${JSON.stringify(path.join(source, "_ui/tokens/index.ts"))};`,
        `import { reviewData } from ${JSON.stringify(path.join(toolRoot, "review-data.ts"))};`,
        `import { componentRecipes } from ${JSON.stringify(path.join(source, "_ui/components/recipes.ts"))};`,
        ...imports,
        `export default { tokens, componentStyles: componentRecipes(tokens), ...reviewData(tokens), styles: {${styleEntries.join(",")}} };`,
      ].join("\n"),
      resolveDir: toolRoot,
      loader: "ts",
    },
    bundle: true,
    platform: "node",
    format: "esm",
    nodePaths: [path.join(toolRoot, "node_modules")],
    outfile: resolveFile,
    logLevel: "warning",
  });
  const { default: data } = await import(`${pathToFileURL(resolveFile).href}?build=${Date.now()}`);
  const stage = path.join(work, "site");
  if ((await lstat(stage).catch(() => null))?.isSymbolicLink()) {
    throw new Error("Refusing to replace a symlinked build stage");
  }
  await rm(stage, { recursive: true, force: true });
  await mkdir(path.join(stage, "assets"), { recursive: true });
  for (const [relative, css] of Object.entries(data.styles)) {
    const output = path.join(stage, relative);
    await mkdir(path.dirname(output), { recursive: true });
    await writeFile(output, css.trim() + "\n");
  }
  await writeFile(path.join(stage, "assets/tokens.json"), JSON.stringify(data.tokens, null, 2) + "\n");
  const entries = inputs.filter((name) => {
    const parts = path.relative(source, name).split(path.sep);
    return path.basename(name) === "index.ts" && !parts.some((part) => part.startsWith("_"));
  });
  if (entries.length) {
    const result = await build({
      absWorkingDir: root,
      entryPoints: entries,
      outbase: source,
      outdir: path.join(stage, "assets"),
      bundle: true,
      format: "esm",
      platform: "browser",
      nodePaths: [path.join(toolRoot, "node_modules")],
      define: { __NW_COMPONENT_STYLES__: JSON.stringify(data.componentStyles) },
      target: "es2022",
      metafile: true,
      logLevel: "warning",
    });
    // A boundary check, not just a size target: Color.js must stay build-only.
    if (Object.keys(result.metafile.inputs).some((name) => name.includes("colorjs.io"))) {
      throw new Error("Color.js leaked into a browser bundle");
    }
    await writeFile(path.join(work, "browser-metafile.json"), JSON.stringify(result.metafile, null, 2) + "\n");
  }
  const dataFile = path.join(work, "render-data.json");
  await writeFile(dataFile, JSON.stringify({ tokens: data.tokens, families: data.families, pairs: data.pairs }));
  execFileSync("uv", [
    "run", "--locked", "--project", toolRoot, "python", path.join(toolRoot, "render.py"),
    "--source", source, "--stage", stage, "--output", path.join(root, "docs"), "--data", dataFile,
  ], { cwd: root, stdio: "inherit" });
  return { data, stage };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  await buildSite();
  console.log("Built docs-src/ → docs/ (Engrave + TypeScript/esbuild; Color.js build-time only)");
}
