import { readFile, writeFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';
import { createHash } from 'node:crypto';
import { execFileSync } from 'node:child_process';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const resources = path.join(root, 'apple/Sources/InkuUI/Resources');
const args = process.argv.slice(2);
if (args.length && (args.length !== 2 || args[0] !== '--source-root')) throw new Error('usage: export-web-reference.mjs [--source-root PRODUCT]');
const sourceRoot = args.length ? path.resolve(args[1]) : root;
const sourceDigests = {};
async function sourceFile(name) {
  const data = await readFile(path.join(sourceRoot, name));
  sourceDigests[name] = createHash('sha256').update(data).digest('hex');
  return data.toString('utf8');
}

function script(source) {
  return stripTypeScriptTypes(source, { mode: 'strip' })
    .replace(/^import\s[^;]*;\s*$/gm, '')
    .replace(/^export\s+/gm, '');
}

async function copyFor(language) {
  const source = await sourceFile(`web/src/lib/i18n/${language}.ts`);
  const context = vm.createContext({});
  // Only the versioned locale object is evaluated; no app runtime is imported.
  vm.runInContext(`${script(source)}\nglobalThis.pack = ${language};`, context, { timeout: 5000 });
  const pack = context.pack;
  const texts = Object.fromEntries(Object.entries(pack).filter(([key, value]) =>
    typeof value === 'string'));
  const dynamicTexts = {};
  const dynamicKeys = [];
  for (const [key, value] of Object.entries(pack)) {
    if (typeof value !== 'function') continue;
    dynamicKeys.push(key);
    try {
      const template = value(...Array(value.length).fill('%@'));
      if (typeof template === 'string' && !/NaN|undefined/.test(template)) dynamicTexts[key] = template;
    } catch { /* The manifest retains non-scalar functions for consumer review. */ }
  }
  texts.limitWeightFormat = pack.settingsRenderLimitsWeight('%@', '%@');
  return {
    texts,
    dynamicTexts,
    dynamicKeys,
    vocabulary: pack.appInfoVocabRows,
    limitLabels: pack.settingsRenderLimitLabels,
    limitHints: pack.settingsRenderLimitHints,
    limitGroups: pack.settingsRenderLimitGroups,
    limitGroupSummaries: pack.settingsRenderLimitGroupSummaries ?? {},
    limitGroupTooltips: pack.settingsRenderLimitGroupTooltips,
    limitUnits: pack.settingsRenderLimitUnits ?? {},
  };
}

const canvasSource = await sourceFile('web/src/lib/plugins/system/canvas-aspect/index.ts');
const metadata = canvasSource.match(/^const DISPLAY_METADATA[^=]*= \{[\s\S]*?^\};/m)?.[0];
if (!metadata) throw new Error('canvas_display_metadata_unavailable');
const canvasContext = vm.createContext({});
vm.runInContext(`${script(metadata)}\nglobalThis.metadata = DISPLAY_METADATA;`, canvasContext, { timeout: 5000 });

const page = await sourceFile('web/src/routes/+page.svelte');
const preview = page.match(/^\tfunction saijikiPreview\([\s\S]*?^\t\}/m)?.[0];
if (!preview) throw new Error('saijiki_preview_unavailable');
const surface = await sourceFile('web/src/lib/saijiki-surface.ts');
const languageSource = await sourceFile('web/src/lib/instructionLang.ts');
const vocabulary = JSON.parse(await readFile(path.join(resources, 'saijiki.json'), 'utf8'));
const previewContext = vm.createContext({ uiLanguage: 'ja' });
vm.runInContext(script(languageSource) + '\n' + script(surface) + '\n' +
  'function getLang() { return globalThis.uiLanguage; }\n' + script(preview) +
  '\nglobalThis.previewFor = saijikiPreview;', previewContext, { timeout: 5000 });

const saijikiPreviews = {};
for (const category of vocabulary.categories) {
  for (const word of category.words.filter(item => item.display)) {
    previewContext.uiLanguage = 'ja';
    const japanese = previewContext.previewFor(category.key, word.surface_ja, word.surface_ja, 'ja');
    previewContext.uiLanguage = 'en';
    const english = previewContext.previewFor(category.key, word.surface_ja, word.surface_en ?? word.surface_ja, 'en');
    saijikiPreviews[`${category.key}:${word.surface_ja}`] = {
      svg: japanese.svg, effectJa: japanese.effect, effectEn: english.effect,
      exampleJa: japanese.example, exampleEn: english.example,
    };
  }
}

const reference = {
  schema: 'inku.apple-ui-reference.v1',
  version: (await sourceFile('web/APP_VERSION')).trim(),
  build: (await sourceFile('web/BUILD_NUMBER')).trim(),
  buildDate: new Date().toISOString(),
  versions: {
    ddlSpec: (await sourceFile('server/src/inku_server/layer_versions.py'))
      .match(/^DDL_VERSION = "([^"]+)"/m)?.[1],
    ddlEngine: (await sourceFile('server/src/inku_server/layer_versions.py'))
      .match(/^DDL_ENGINE_VERSION = "([^"]+)"/m)?.[1],
    renderEngine: (await sourceFile('core/crates/inku-render/src/lib.rs'))
      .match(/pub const RENDER_ENGINE_VERSION: &str = "([^"]+)"/)?.[1],
  },
  canvasMetadata: canvasContext.metadata,
  copy: { ja: await copyFor('ja'), en: await copyFor('en') },
  saijikiPreviews,
};
if (Object.values(reference.versions).some(value => !value)) throw new Error('product_layer_versions_unavailable');
reference.source = {
  commit: execFileSync('git', ['-C', sourceRoot, 'rev-parse', 'HEAD'], { encoding: 'utf8' }).trim(),
  files: sourceDigests,
  tooltipKeys: Object.keys(reference.copy.ja.texts).filter(key => /^tooltips?/.test(key)).sort(),
};
await writeFile(path.join(resources, 'ui-reference.json'), JSON.stringify(reference, null, 2) + '\n');
console.log(`Generated Web reference copy, canvas metadata and ${Object.keys(saijikiPreviews).length} Saijiki previews.`);
