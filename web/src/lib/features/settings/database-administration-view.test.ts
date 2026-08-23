// Run with the focused Stage 3B command in the contract.
//
// This source-level seam keeps database and backup presentation beside the
// Settings feature while the route-instance controller remains the only state
// and operation owner.
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const VIEW_URL = new URL('./DatabaseAdministrationSettings.svelte', import.meta.url);
const VIEW = existsSync(VIEW_URL) ? read('./DatabaseAdministrationSettings.svelte') : '';
const OWNER = read('./server-administration.svelte.ts');
const MODAL = read('../../components/SettingsModal.svelte');
const DB_BRANCH = MODAL.slice(
	MODAL.indexOf("{:else if settingsTab === 'db'}"),
	MODAL.indexOf("{:else if settingsTab === 'server_misc'}")
);

test('Stage 3B gives database and backup presentation one feature-local view', () => {
	assert.notEqual(VIEW, '', 'DatabaseAdministrationSettings.svelte');
	assert.match(MODAL, /import DatabaseAdministrationSettings from '\$lib\/features\/settings\/DatabaseAdministrationSettings\.svelte'/);
	assert.match(DB_BRANCH, /<DatabaseAdministrationSettings/);
	assert.doesNotMatch(DB_BRANCH, /settingsCurrentDb|settingsDbBackupTitle|db-backup-list/);
	for (const helper of ['formatBytes', 'formatTimestamp', 'dbBackupEstimatedBytes', 'saveDbBackupSettings']) {
		assert.match(VIEW, new RegExp(helper), helper);
		assert.doesNotMatch(MODAL, new RegExp(`(?:function|const) ${helper}\\b`), helper);
	}
});

test('the focused view receives only database slices and named capabilities', () => {
	assert.match(VIEW, /type DatabaseStatus = Pick<SettingsStatus, 'database' \| 'db_backup'>;/);
	assert.match(VIEW, /status: DatabaseStatus \| null;/);
	assert.doesNotMatch(VIEW, /SettingsController|apiFetch|\/api\//);
	assert.match(DB_BRANCH, /status=\{settingsStatus \? \{ database: settingsStatus\.database, db_backup: settingsStatus\.db_backup \} : null\}/);
	for (const capability of ['onReload', 'onUpdateBackupSettings', 'onRunBackupNow']) {
		assert.match(VIEW, new RegExp(`${capability}:`), capability);
		assert.match(DB_BRANCH, new RegExp(`${capability}=`), capability);
	}
	for (const owner of ['loadSettingsStatus', 'updateDbBackupSettings', 'runDbBackupNow']) {
		assert.match(OWNER, new RegExp(`async function ${owner}\\(`), owner);
		assert.doesNotMatch(VIEW, new RegExp(`(?:async\\s+)?function ${owner}\\(`), owner);
	}
});

test('database-specific styles move while shared grid support remains available', () => {
	for (const selector of ['.db-backup-field', '.db-backup-time', '.db-backup-list-wrap', '.db-backup-list']) {
		assert.match(VIEW, new RegExp(selector.replace('.', '\\.') + '\\s*\\{'), selector);
		assert.doesNotMatch(MODAL, new RegExp(selector.replace('.', '\\.') + '\\s*\\{'), selector);
	}
	assert.match(VIEW, /\.db-backup-grid\s*\{/);
	assert.match(MODAL, /\.db-backup-grid\s*\{/);
	assert.equal((VIEW.match(/:global\(/g) ?? []).length, 1);
	assert.match(VIEW, /\.db-backup-time-fields :global\(\.number-stepper\)/);
});
