// Run with the focused Stage 2A command in the contract.
//
// This is an ownership characterization rather than a UI snapshot. It keeps
// the Settings controller route-scoped, makes the page a composition root, and
// prevents the modal boundary from regressing to individual admin props.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const OWNER = read('./state.svelte.ts');
const SERVER_OWNER = read('./server-administration.svelte.ts');
const MODEL_OWNER = read('./model-administration.svelte.ts');
const USER_OWNER = read('./user-administration.svelte.ts');
const ALL_OWNERS = OWNER + SERVER_OWNER + MODEL_OWNER + USER_OWNER;
const PAGE = read('../../../routes/+page.svelte');
const MODAL = read('../../components/SettingsModal.svelte');
const MODEL_VIEW = read('./ModelAdministrationSettings.svelte');

const MOVED_PAGE_WRITERS = [
	'settingsOpen',
	'settingsMode',
	'settingsTab',
	'settingsDetail',
	'settingsStatus',
	'settingsStatusError',
	'settingsStatusLoading',
	'dbBackupStatus',
	'outputSaveStatus',
	'logRetentionStatus',
	'renderLimitsStatus',
	'pluginActionStatus',
	'renderConcurrencyStatus'
];

test('Stage 2A gives Settings shell and server administration one route-instance owner', () => {
	assert.match(OWNER, /export function createSettingsController/);
	assert.match(PAGE, /createSettingsController\(\{/);
	assert.equal((PAGE.match(/createSettingsController\(\{/g) ?? []).length, 1);
	assert.doesNotMatch(OWNER, /^\s*export const settings\s*=/m);
	for (const name of MOVED_PAGE_WRITERS) {
		assert.doesNotMatch(PAGE, new RegExp(`let ${name}\\s*=\\s*\\$state`), name);
	}
});

test('the page no longer owns moved Settings operations or endpoints', () => {
	for (const name of [
		'loadSettingsStatus',
		'updateDbBackupSettings',
		'runDbBackupNow',
		'updateOutputSaveSettings',
		'updateRenderConcurrencySettings',
		'updateLogRetentionSettings',
		'updateRenderLimits'
	]) {
		assert.doesNotMatch(PAGE, new RegExp(`(?:async\\s+)?function ${name}\\(`), name);
	}
	for (const endpoint of [
		'/api/settings/status',
		'/api/settings/db-backup',
		'/api/settings/output-save',
		'/api/settings/render-concurrency',
		'/api/settings/log-retention',
		'/api/settings/limits'
	]) {
		assert.doesNotMatch(PAGE, new RegExp(endpoint.replaceAll('/', '\\/')));
		assert.match(SERVER_OWNER, new RegExp(endpoint.replaceAll('/', '\\/')));
	}
});

test('SettingsModal receives one typed Stage 2A boundary and no generic transport', () => {
	assert.match(MODAL, /settings: SettingsController;/);
	assert.match(MODAL, /import type \{[\s\S]*SettingsController,[\s\S]*\} from '\$lib\/features\/settings\/state\.svelte'/);
	assert.match(PAGE, /<SettingsModal[\s\S]*settings=\{settings\}/);
	assert.doesNotMatch(MODAL, /apiFetch\s*:/);
	for (const prop of [
		'settingsStatus:',
		'settingsStatusError:',
		'settingsStatusLoading:',
		'pluginActionStatus:',
		'onLoadSettingsStatus:',
		'onUpdateRenderLimits:'
	]) {
		assert.doesNotMatch(MODAL.slice(MODAL.indexOf('type Props'), MODAL.indexOf('}: Props = $props()')), new RegExp(prop));
	}
});

test('user edit secrets do not enter the Settings owner', () => {
	for (const field of ['loginPassword', 'newUserPassword', 'editUserPassword']) {
		assert.doesNotMatch(ALL_OWNERS, new RegExp(field), field);
	}
	assert.doesNotMatch(ALL_OWNERS, /newProviderApiKey/);
	assert.match(MODEL_VIEW, /let newProviderApiKey = \$state\(''\)/);
});
