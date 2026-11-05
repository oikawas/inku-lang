import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { ja } from '../i18n/ja.ts';
import { DRAW_OPTIONS, TEXT_ONLY_OPTIONS, copyDrawOptions, drawOptionRows, type DrawOptions, type RecordedDrawOptions } from './draw-options.ts';

// The one list of options lives in the core's release file; the Web wiring is
// checked against it, so a key added there and not wired here fails.
const release = JSON.parse(readFileSync(new URL('../../../../core/crates/inku-pipeline/data/release-defaults.json', import.meta.url), 'utf8')) as
	{ tabs: Record<string, Record<string, unknown>> };
const coreKeys = Object.keys(release.tabs.describe);
const settings = readFileSync(new URL('./settings/DrawDefaultsSettings.svelte', import.meta.url), 'utf8');
const page = readFileSync(new URL('../../routes/+page.svelte', import.meta.url), 'utf8');
const state = readFileSync(new URL('./work/state.svelte.ts', import.meta.url), 'utf8');

const sample: DrawOptions = { route: 'stages', sketch: 'on', composition: 'on', wild: 'on',
	catalog: { id: 'default', mode: 'fixed' }, canvas_aspect: 'square', models: { stage1: 'openai:a', stage2: 'openai:a' } };
const record: RecordedDrawOptions = { route: 'read_and_draw', sketch: 'on', composition: 'off', wild: 'off',
	catalog: { id: 'sumi', mode: 'auto' }, canvas_aspect: 'a4', models: { stage1: 'openai:b', stage2: 'openai:b' } };

test('the Web knows exactly the core\'s options, and every tab of the release names them all', () => {
	assert.deepEqual([...DRAW_OPTIONS].sort(), [...coreKeys].sort());
	for (const options of Object.values(release.tabs)) assert.deepEqual(Object.keys(options).sort(), [...coreKeys].sort());
});

for (const key of coreKeys) {
	test(`${key} is shown on the strip, set in Settings, reset by New and adopted through the core`, () => {
		const rows = drawOptionRows(record, ja);
		assert.notEqual(rows.find((row) => row.key === key)?.text, ja.drawOptionsUnavailable);
		assert.ok(settings.includes(`data-draw-option="${key}"`));
		assert.deepEqual(copyDrawOptions(sample)[key as keyof DrawOptions], sample[key as keyof DrawOptions]);
	});
}

test('opening a work adopts the core\'s answer whole; the Web keeps no copy of the rule', () => {
	assert.match(page, /\/api\/auth\/me\/draw-options\/for-tab/);
	assert.match(state, /drawChoices\[tab\] = copyDrawOptions\(options\)/);
	assert.doesNotMatch(state + page, /optionsForWork/);
});

test('an unrecorded choice reads N/A; a picture shows no route, sketch or composition row', () => {
	assert.ok(drawOptionRows(null, ja).every((row) => row.text === ja.drawOptionsUnavailable));
	const image = drawOptionRows({ ...record, models: { vision: 'openai:v' } }, ja, { image: true }).map((row) => row.key);
	for (const key of TEXT_ONLY_OPTIONS) assert.ok(!image.includes(key), key);
	assert.ok(image.includes('wild') && image.includes('models'));
});

test('rows name catalogs, canvases and models when told how', () => {
	const rows = drawOptionRows(record, ja, { names: { catalog: () => 'Sumi', canvas: () => 'A4', model: () => 'Model B' } });
	assert.equal(rows.find((row) => row.key === 'catalog')?.text, `Sumi (${ja.colorCatalogAuto})`);
	assert.equal(rows.find((row) => row.key === 'canvas_aspect')?.text, 'A4');
	assert.equal(rows.find((row) => row.key === 'models')?.text, 'Model B');
});

test('the old browser stroke-limit default is only removed, never saved', () => {
	assert.match(page, /localStorage\.removeItem\(LEGACY_WILD_DEFAULT_KEY\)/);
	assert.doesNotMatch(page, /migrateLegacyWild|saveDrawDefaults\(defaults\)\.then/);
});

test('settings expose a separate page and use the existing model picker', () => {
	const modal = readFileSync(new URL('../components/SettingsModal.svelte', import.meta.url), 'utf8');
	const nav = readFileSync(new URL('./settings/navigation-state.svelte.ts', import.meta.url), 'utf8');
	assert.match(modal, /onSelectSettingsTab\('draw_defaults'\)/);
	assert.match(modal, /settingsTab === 'draw_defaults'[^]*<DrawDefaultsSettings/);
	assert.match(modal, /case 'draw_defaults': return \{ title: strings\.drawDefaultsTitle, hint: strings\.drawDefaultsHint \}/);
	assert.match(nav, /BROWSER_ONLY_SETTINGS_TABS[^]*'draw_defaults'/);
	assert.match(settings, /<ModelSelectionSettings/);
	assert.match(modal, /<DrawDefaultsSettings[^>]*providerGroups=\{drawingProviderGroups\}/);
	assert.match(page, /drawingProviderGroups=\{availableModelCatalog\}/);
	assert.doesNotMatch(settings, /<input/);
	assert.match(settings, /\{#if !image\}[^]*data-draw-option="route"[^]*data-draw-option="wild"[^]*\{\/if\}/);
	assert.match(settings, /<option value="auto">\{t\(\)\.colorCatalogAuto\}<\/option>/);
});
