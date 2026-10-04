import { readFile, writeFile } from 'node:fs/promises';
import { stripTypeScriptTypes } from 'node:module';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import vm from 'node:vm';

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '../..');
const resources = path.join(root, 'apple/Sources/InkuUI/Resources');

function script(source) {
  return stripTypeScriptTypes(source, { mode: 'strip' })
    .replace(/^import\s[^;]*;\s*$/gm, '')
    .replace(/^export\s+/gm, '');
}

async function copyFor(language) {
  const source = await readFile(path.join(root, `web/src/lib/i18n/${language}.ts`), 'utf8');
  const context = vm.createContext({});
  // Only the versioned locale object is evaluated; no app runtime is imported.
  vm.runInContext(`${script(source)}\nglobalThis.pack = ${language};`, context, { timeout: 5000 });
  const pack = context.pack;
  const texts = Object.fromEntries(Object.entries(pack).filter(([key, value]) =>
    typeof value === 'string' && /^(appInfo|saijiki|settingsRenderLimit|tooltips)/.test(key)));
  texts.limitWeightFormat = pack.settingsRenderLimitsWeight('%@', '%@');
  return {
    texts,
    vocabulary: pack.appInfoVocabRows,
    limitLabels: pack.settingsRenderLimitLabels,
    limitHints: pack.settingsRenderLimitHints,
    limitGroups: pack.settingsRenderLimitGroups,
    limitGroupSummaries: pack.settingsRenderLimitGroupSummaries ?? {},
    limitGroupTooltips: pack.settingsRenderLimitGroupTooltips,
    limitUnits: pack.settingsRenderLimitUnits ?? {},
  };
}

const canvasSource = await readFile(path.join(root, 'web/src/lib/plugins/system/canvas-aspect/index.ts'), 'utf8');
const metadata = canvasSource.match(/^const DISPLAY_METADATA[^=]*= \{[\s\S]*?^\};/m)?.[0];
if (!metadata) throw new Error('canvas_display_metadata_unavailable');
const canvasContext = vm.createContext({});
vm.runInContext(`${script(metadata)}\nglobalThis.metadata = DISPLAY_METADATA;`, canvasContext, { timeout: 5000 });

const page = await readFile(path.join(root, 'web/src/routes/+page.svelte'), 'utf8');
const preview = page.match(/^\tfunction saijikiPreview\([\s\S]*?^\t\}/m)?.[0];
if (!preview) throw new Error('saijiki_preview_unavailable');
const surface = await readFile(path.join(root, 'web/src/lib/saijiki-surface.ts'), 'utf8');
const languageSource = await readFile(path.join(root, 'web/src/lib/instructionLang.ts'), 'utf8');
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
  version: (await readFile(path.join(root, 'web/APP_VERSION'), 'utf8')).trim(),
  build: (await readFile(path.join(root, 'web/BUILD_NUMBER'), 'utf8')).trim(),
  buildDate: new Date().toISOString(),
  versions: {
    ddlSpec: (await readFile(path.join(root, 'server/src/inku_server/layer_versions.py'), 'utf8'))
      .match(/^DDL_VERSION = "([^"]+)"/m)?.[1],
    ddlEngine: (await readFile(path.join(root, 'server/src/inku_server/layer_versions.py'), 'utf8'))
      .match(/^DDL_ENGINE_VERSION = "([^"]+)"/m)?.[1],
    renderEngine: (await readFile(path.join(root, 'core/crates/inku-render/src/lib.rs'), 'utf8'))
      .match(/pub const RENDER_ENGINE_VERSION: &str = "([^"]+)"/)?.[1],
  },
  canvasMetadata: canvasContext.metadata,
  copy: { ja: await copyFor('ja'), en: await copyFor('en') },
  saijikiPreviews,
};
if (Object.values(reference.versions).some(value => !value)) throw new Error('product_layer_versions_unavailable');
await writeFile(path.join(resources, 'ui-reference.json'), JSON.stringify(reference, null, 2) + '\n');
console.log(`Generated Web reference copy, canvas metadata and ${Object.keys(saijikiPreviews).length} Saijiki previews.`);
