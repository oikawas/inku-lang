import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string): string => {
	try { return readFileSync(new URL(path, import.meta.url), 'utf8'); }
	catch { return ''; }
};

test('T-1001/T-1002: SettingsModal composes each focused Settings view once', () => {
	const modal = read('../../components/SettingsModal.svelte');
	for (const view of [
		'ModelSelectionSettings',
		'ModelAdministrationSettings',
		'PluginAdministrationSettings',
		'ExportSettings',
		'AppearanceSettings'
	]) {
		assert.match(modal, new RegExp(`import ${view} from '\\$lib/features/settings/${view}\\.svelte'`));
		assert.equal((modal.match(new RegExp(`<${view}\\b`, 'g')) ?? []).length, 1, view);
	}
});

test('T-1002/T-1006: drafts and helpers live with their focused views', () => {
	const modal = read('../../components/SettingsModal.svelte');
	const model = read('./ModelAdministrationSettings.svelte');
	const plugin = read('./PluginAdministrationSettings.svelte');
	const appearance = read('./AppearanceSettings.svelte');

	for (const name of ['newProviderApiKey', 'modelPickerEnabledDraft', 'openModelPicker']) {
		assert.match(model, new RegExp(name), name);
		assert.doesNotMatch(modal, new RegExp(name), name);
	}
	for (const name of ['pluginEditorContent', 'pluginDeleteConfirmId', 'openPluginEditor']) {
		assert.match(plugin, new RegExp(name), name);
		assert.doesNotMatch(modal, new RegExp(name), name);
	}
	assert.match(appearance, /historyStripFields/);
	for (const view of [model, plugin, appearance, read('./ModelSelectionSettings.svelte'), read('./ExportSettings.svelte')]) {
		assert.doesNotMatch(view, /SettingsController/);
	}
});

test('T-1002: shared Settings primitives stay behind one feature boundary', () => {
	const modal = read('../../components/SettingsModal.svelte');
	const css = read('./settings-modal.css');
	assert.equal((modal.match(/import '\$lib\/features\/settings\/settings-modal\.css';/g) ?? []).length, 1);
	assert.match(modal, /<div class="settings-feature-root">/);
	assert.match(css, /^\.settings-feature-root \{/);
	assert.match(css, /\.settings-feature-root \.settings-modal/);
	assert.doesNotMatch(css, /:global/);
	for (const [view, stylesheet] of [
		['ModelSelectionSettings', 'model-selection-settings'],
		['ModelAdministrationSettings', 'model-administration-settings'],
		['PluginAdministrationSettings', 'plugin-administration-settings'],
		['ExportSettings', 'export-settings'],
		['AppearanceSettings', 'appearance-settings']
	]) {
		assert.match(read(`./${view}.svelte`), new RegExp(`import './${stylesheet}\\.css';`), view);
		assert.match(read(`./${stylesheet}.css`), /\.settings-feature-root /, stylesheet);
	}
});
