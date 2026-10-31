import { build } from "esbuild";
import { execFileSync } from "node:child_process";
import { mkdir, readdir, readFile, rm, writeFile, lstat } from "node:fs/promises";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const toolRoot = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(toolRoot, "../../..");
const source = path.join(root, "src/docs-src");
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
export async function buildSite({ version = "dev", includeDesign = false, dev = false, mode = "local", stableVersion } = {}) {
  if (version !== "dev" && !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(version)) {
    throw new Error("Version must be dev or a strict major.minor.patch identifier");
  }
  if (!["local", "artifact"].includes(mode)) throw new Error("Mode must be local or artifact");
  if (mode === "artifact" && (!stableVersion || !/^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)$/.test(stableVersion))) {
    throw new Error("Artifact root requires an explicit verified existing --stable-version");
  }
  // Legacy dev means design playground, never a documentation version.
  includeDesign ||= dev;
  await mkdir(work, { recursive: true });
  const inputs = (await files(source)).filter(name => includeDesign || path.relative(source, name).split(path.sep)[0] !== "design");
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
      splitting: true,
      minify: true,
      keepNames: true, // Preserve Adapter/custom-element class identities and diagnostics.
      chunkNames: "chunks/[name]-[hash]",
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
    // Distribute the installed upstream license/notice files for shipped runtime packages.
    const packages = new Map();
    for (const input of Object.keys(result.metafile.inputs).filter(name => name.includes("node_modules/"))) {
      let directory = path.dirname(path.resolve(root, input));
      while (directory !== root) {
        const manifest = await readFile(path.join(directory, "package.json"), "utf8").catch(() => null);
        if (manifest) {
          const info = JSON.parse(manifest);
          if (info.name && info.version) { packages.set(`${info.name}@${info.version}`, directory); break; }
        }
        directory = path.dirname(directory);
      }
    }
    const notices = ["Third-party runtime licenses (generated from the locked installed packages)."];
    for (const [name, directory] of [...packages].sort(([a], [b]) => a.localeCompare(b, "en"))) {
      const licenses = (await readdir(directory)).filter(name => /^(licen[sc]e|notices?)([.\-_]|$)/i.test(name)).sort();
      if (!licenses.length) throw new Error(`Missing runtime license for ${name}`);
      for (const license of licenses) notices.push(`\n## ${name} / ${license}\n\n${await readFile(path.join(directory, license), "utf8")}`);
    }
    const licenses = path.join(stage, "assets/licenses/runtime");
    await mkdir(licenses, { recursive: true });
    await writeFile(path.join(licenses, "NOTICE.txt"), notices.join("\n") + "\n");
  }
  const dataFile = path.join(work, "render-data.json");
  await writeFile(dataFile, JSON.stringify({ tokens: data.tokens, families: data.families, pairs: data.pairs }));
  execFileSync("uv", [
    "run", "--locked", "--project", toolRoot, "python", path.join(toolRoot, "render.py"),
    "--source", source, "--stage", stage, "--output", path.join(root, "docs"), "--data", dataFile,
    "--version", version, "--mode", mode,
    ...(stableVersion ? ["--stable-version", stableVersion] : []),
    ...(includeDesign ? ["--include-design"] : []),
  ], { cwd: root, stdio: "inherit" });
  return { data, stage, output: path.join(root, "docs", version) };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const options = {};
  for (let i = 0; i < args.length; i++) {
    const arg = args[i];
    if (arg === "--include-design" || arg === "--dev") options.includeDesign = true;
    else if (["--version", "--mode", "--stable-version"].includes(arg) && args[i + 1] && !args[i + 1].startsWith("--")) {
      options[{ "--version": "version", "--mode": "mode", "--stable-version": "stableVersion" }[arg]] = args[++i];
    } else throw new Error("Usage: node build.mjs [--version dev|X.Y.Z] [--include-design] [--mode local|artifact] [--stable-version X.Y.Z]");
  }
  await buildSite(options);
  console.log(`Built src/docs-src/ → docs/${options.version ?? "dev"}/ (${options.includeDesign ? "with design playground" : "product only"}; ${options.mode ?? "local"} root policy)`);
}
