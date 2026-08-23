// Run with the focused Stage 3A command in the contract.
//
// This source-level seam keeps the account view beside its Settings owner,
// passes only the account submodel, and keeps input drafts out of both the
// route and the canonical administration state.
import assert from 'node:assert/strict';
import { existsSync, readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const VIEW_URL = new URL('./UserAdministrationSettings.svelte', import.meta.url);
const VIEW = existsSync(VIEW_URL) ? read('./UserAdministrationSettings.svelte') : '';
const OWNER = read('./state.svelte.ts');
const USER_OWNER = read('./user-administration.svelte.ts');
const MODAL = read('../../components/SettingsModal.svelte');
const PAGE = read('../../../routes/+page.svelte');
const USER_BRANCH = MODAL.slice(
	MODAL.indexOf("{:else if settingsTab === 'users'}"),
	MODAL.indexOf("{:else if settingsTab === 'unread'}")
);
const PUBLIC_CONTROLLER = OWNER.slice(OWNER.lastIndexOf('\n\treturn {'));

test('Stage 3A gives the cohesive account view one feature-local component', () => {
	assert.notEqual(VIEW, '', 'UserAdministrationSettings.svelte');
	assert.match(MODAL, /import UserAdministrationSettings from '\$lib\/features\/settings\/UserAdministrationSettings\.svelte'/);
	assert.match(USER_BRANCH, /<UserAdministrationSettings/);
	assert.doesNotMatch(USER_BRANCH, /class="(?:login-grid|user-management-layout|group-list)"/);
	for (const draft of ['newUserPassword', 'editUserPassword', 'selectedUserId', 'newGroupName', 'editGroupId']) {
		assert.match(VIEW, new RegExp(`let ${draft}(?:\\s*:[^=]+)?\\s*=\\s*\\$state`), draft);
		assert.doesNotMatch(MODAL, new RegExp(`let ${draft}(?:\\s*:[^=]+)?\\s*=\\s*\\$state`), draft);
	}
});

test('the focused view receives only the account submodel and session capabilities', () => {
	assert.match(USER_OWNER, /export type SettingsUserAdministration\s*=\s*\{/);
	assert.match(PUBLIC_CONTROLLER, /\buserAdministration,/);
	assert.doesNotMatch(PUBLIC_CONTROLLER, /get users\(|get groups\(|loadUserAdministration,|addUser,|updateUser,|removeUser,/);
	assert.match(VIEW, /administration: SettingsUserAdministration;/);
	assert.doesNotMatch(VIEW, /SettingsController|apiFetch|\/api\//);
	assert.doesNotMatch(MODAL, /const users = \$derived\(settings\.users\)/);
	assert.match(PAGE, /settings\.userAdministration\.(?:load|users|groups)/);
});

test('account-specific styles move with the view without becoming global', () => {
	for (const selector of ['.login-grid', '.user-management-layout', '.user-row', '.group-row']) {
		assert.match(VIEW, new RegExp(selector.replace('.', '\\.') + '\\s*\\{'), selector);
		assert.doesNotMatch(MODAL, new RegExp(selector.replace('.', '\\.') + '\\s*\\{'), selector);
	}
	for (const primitive of ['.popover-group', '.popover-group-label', '.inline-message', '.db-test-result', '.primary-inline']) {
		assert.match(VIEW, new RegExp(primitive.replace('.', '\\.') + '\\s*\\{'), primitive);
	}
	assert.doesNotMatch(VIEW, /:global\(/);
});
