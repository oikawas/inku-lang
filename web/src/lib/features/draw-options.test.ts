import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { ja } from '../i18n/ja.ts';
import { DRAW_OPTIONS, copyDrawOptions, drawOptionRows, migrateLegacyWild, optionsForWork, type DrawOptions, type RecordedDrawOptions } from './draw-options.ts';

const defaults: DrawOptions = { route: 'stages', sketch: 'on', composition: 'on', wild: 'on',
	catalog: { id: 'default', mode: 'fixed' }, canvas_aspect: 'square', models: { stage1: 'openai:a', stage2: 'openai:a' } };
const record: RecordedDrawOptions = { route: 'read_and_draw', sketch: 'on', composition: 'off', wild: 'off',
	catalog: { id: 'sumi', mode: 'auto' }, canvas_aspect: 'a4', models: { stage1: 'openai:b', stage2: 'openai:b' } };
const settings = readFileSync(new URL('./settings/DrawDefaultsSettings.svelte', import.meta.url), 'utf8');

for (const key of DRAW_OPTIONS) {
	test(`${key} is displayed, restored, configurable and reset from defaults`, () => {
		const rows = drawOptionRows(record, ja);
		assert.equal(rows.find((row) => row.key === key)?.text === 'N/A', false);
		assert.deepEqual(optionsForWork(record, defaults, 'describe')[key], record[key]);
		assert.ok(settings.includes(`data-draw-option="${key}"`));
		const reset = copyDrawOptions(defaults);
		assert.deepEqual(reset[key], defaults[key]);
	});
}

test('missing choices stay N/A and restore only switches as off', () => {
	assert.ok(drawOptionRows(null, ja).every((row) => row.text === 'N/A'));
	assert.deepEqual(optionsForWork(null, defaults, 'describe'), { ...defaults, sketch: 'off', composition: 'off', wild: 'off' });
});

test('legacy wild default is copied to all tabs without changing the originals', () => {
	const all = { describe: defaults, image: defaults, batch_text: defaults, batch_image: defaults };
	const migrated = migrateLegacyWild(all, '0');
	assert.ok(migrated);
	assert.ok(Object.values(migrated).every((tab) => tab.wild === 'off'));
	assert.equal(defaults.wild, 'on');
	assert.equal(migrateLegacyWild(all, null), null);
});


test('settings expose a separate page and use the existing model picker', () => {
	const modal = readFileSync(new URL('../components/SettingsModal.svelte', import.meta.url), 'utf8');
	const nav = readFileSync(new URL('./settings/navigation-state.svelte.ts', import.meta.url), 'utf8');
	assert.match(modal, /onSelectSettingsTab\('draw_defaults'\)/);
	assert.match(modal, /settingsTab === 'draw_defaults'[^]*<DrawDefaultsSettings/);
	assert.match(nav, /BROWSER_ONLY_SETTINGS_TABS[^]*'draw_defaults'/);
	assert.match(settings, /<ModelSelectionSettings/);
	assert.doesNotMatch(settings, /<input/);
	assert.match(settings, /\{#if !image\}[^]*data-draw-option="route"[^]*data-draw-option="wild"[^]*\{\/if\}/);
	assert.match(settings, /<option value="auto">\{t\(\)\.colorCatalogAuto\}<\/option>/);
});
