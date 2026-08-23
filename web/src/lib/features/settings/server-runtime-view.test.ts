// Run with the focused Stage 3D command in the contract.
//
// This seam keeps server-runtime presentation beside the Settings feature
// without moving canonical status, persistence, or client-fanout ownership.
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const VIEW_URL = new URL('./ServerRuntimeSettings.svelte', import.meta.url);
const VIEW = existsSync(VIEW_URL) ? read('./ServerRuntimeSettings.svelte') : '';
const OWNER = read('./server-administration.svelte.ts');
const MODAL = read('../../components/SettingsModal.svelte');
const SERVER_BRANCH = MODAL.slice(
	MODAL.indexOf("{:else if settingsTab === 'server_misc'}"),
	MODAL.indexOf("{:else if settingsTab === 'logs'}")
);

test('Stage 3D gives server-runtime presentation one feature-local view', () => {
	assert.notEqual(VIEW, '', 'ServerRuntimeSettings.svelte');
	assert.match(MODAL, /import ServerRuntimeSettings from '\$lib\/features\/settings\/ServerRuntimeSettings\.svelte'/);
	assert.match(SERVER_BRANCH, /<ServerRuntimeSettings/);
	assert.doesNotMatch(SERVER_BRANCH, /settingsOutputSaveTitle|settingsRenderConcurrencyTitle|server-path-row/);
});

test('the focused view receives two status slices and named capabilities', () => {
	assert.match(VIEW, /type ServerRuntimeStatus = Pick<SettingsStatus, 'output_save' \| 'render_concurrency'>;/);
	assert.match(VIEW, /status: ServerRuntimeStatus \| null;/);
	assert.doesNotMatch(VIEW, /SettingsController|apiFetch|\/api\//);
	assert.match(SERVER_BRANCH, /status=\{settingsStatus \? \{ output_save: settingsStatus\.output_save, render_concurrency: settingsStatus\.render_concurrency \} : null\}/);
	for (const capability of ['onReload', 'onUpdateOutputSave', 'onUpdateRenderConcurrency']) {
		assert.match(VIEW, new RegExp(capability + ':'), capability);
		assert.match(SERVER_BRANCH, new RegExp(capability + '='), capability);
	}
	for (const owner of ['loadSettingsStatus', 'updateOutputSaveSettings', 'updateRenderConcurrencySettings']) {
		assert.match(OWNER, new RegExp('async function ' + owner + '\\('), owner);
		assert.doesNotMatch(VIEW, new RegExp('(?:async\\s+)?function ' + owner + '\\('), owner);
	}
	assert.match(OWNER, /Apply the client limit to this tab immediately/);
});

test('server-runtime-specific styles move without globalizing shared primitives', () => {
	for (const selector of ['.server-path-row', '.server-path-input-row', '.info-dot', '.info-tooltip']) {
		assert.match(VIEW, new RegExp(selector.replace('.', '\\.') + '\\s*\\{'), selector);
		assert.doesNotMatch(MODAL, new RegExp(selector.replace('.', '\\.') + '\\s*\\{'), selector);
	}
	for (const shared of ['.popover-group', '.settings-readonly-grid', '.inline-message']) {
		assert.match(VIEW, new RegExp(shared.replace('.', '\\.') + '\\s*\\{'), shared);
		assert.match(MODAL, new RegExp(shared.replace('.', '\\.') + '\\s*\\{'), shared);
	}
	assert.match(VIEW, /\.settings-readonly-grid \.nowrap-label/);
	assert.doesNotMatch(MODAL, /\.settings-readonly-grid \.nowrap-label/);
	assert.equal((VIEW.match(/:global\(/g) ?? []).length, 0);
	assert.doesNotMatch(VIEW, /^[\t ]*(?:\/\/|\/\*|\*|<!--).*[぀-ヿ㐀-鿿]/m);
});
