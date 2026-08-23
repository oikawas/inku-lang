// Run with the focused Stage 2C command in the contract.
//
// This source-level seam keeps account administration in the route-instance
// Settings owner while session identity stays on the page and unsaved form
// values, especially passwords, stay inside the focused view that owns the inputs.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const OWNER = read('./state.svelte.ts');
const USER_OWNER = read('./user-administration.svelte.ts');
const PAGE = read('../../../routes/+page.svelte');
const MODAL = read('../../components/SettingsModal.svelte');
const VIEW = read('./UserAdministrationSettings.svelte');
const PROPS = MODAL.slice(MODAL.indexOf('type Props'), MODAL.indexOf('}: Props = $props()'));

test('Stage 2C gives user and group administration one Settings owner', () => {
	for (const name of ['users', 'groups', 'userAdministrationStatus', 'userAdministrationLoading', 'userAdministrationRequestId']) {
		assert.doesNotMatch(PAGE, new RegExp(`let ${name}(?:\\s*:[^=]+)?\\s*=`), name);
		assert.match(USER_OWNER, new RegExp(`let ${name}(?:\\s*:[^=]+)?\\s*=`), name);
	}
	for (const name of ['loadUserAdministration', 'addUser', 'updateUser', 'removeUser', 'addGroup', 'removeGroup', 'updateGroup']) {
		assert.doesNotMatch(PAGE, new RegExp(`(?:async\\s+)?function ${name}\\(`), name);
		assert.match(USER_OWNER, new RegExp(`(?:async\\s+)?function ${name}\\(`), name);
	}
	for (const endpoint of ['/api/users', '/api/user-groups']) {
		assert.doesNotMatch(PAGE, new RegExp(endpoint.replaceAll('/', '\\/')));
		assert.match(USER_OWNER, new RegExp(endpoint.replaceAll('/', '\\/')));
	}
});

test('user administration types and focused view boundary are canonical on SettingsController', () => {
	for (const typeName of ['SettingsUserItem', 'SettingsUserGroup', 'CreateSettingsUserInput', 'UpdateSettingsUserInput']) {
		assert.match(USER_OWNER, new RegExp(`export type ${typeName}`));
		assert.doesNotMatch(MODAL, new RegExp(`type ${typeName}`));
	}
	for (const prop of [
		'userSettingsStatus:', 'userSettingsLoading:', 'users:', 'groups:',
		'onLoadUserSettings:', 'onAddUser:', 'onSetEditUser:', 'onClearEditUser:',
		'onSaveUserEdit:', 'onRemoveUser:', 'onAddGroup:', 'onRemoveGroup:',
		'onSetEditGroup:', 'onClearEditGroup:', 'onSaveGroupEdit:'
	]) {
		assert.doesNotMatch(PROPS, new RegExp(prop), prop);
	}
	assert.match(OWNER, /readonly userAdministration: SettingsUserAdministration/);
	assert.match(MODAL, /administration=\{settings\.userAdministration\}/);
	assert.match(VIEW, /administration\.load/);
	assert.match(VIEW, /administration\.addUser/);
	assert.match(VIEW, /administration\.updateGroup/);
});

test('session identity stays page-owned behind one named refresh capability', () => {
	assert.match(PAGE, /let currentUser(?:\s*:[^=]+)?\s*=\s*\$state/);
	assert.match(PAGE, /async function login\(/);
	assert.match(PAGE, /async function logout\(/);
	assert.match(PAGE, /async function refreshCurrentUserSettings\(/);
	assert.doesNotMatch(OWNER, /let currentUser(?:\s*:[^=]+)?\s*=\s*\$state/);
	assert.doesNotMatch(OWNER, /function (?:login|logout)\(/);
	assert.match(USER_OWNER, /refreshCurrentUserSettings:/);
	assert.match(USER_OWNER, /await deps\.refreshCurrentUserSettings\(\)/);
	assert.match(PAGE, /refreshCurrentUserSettings,/);
	assert.match(PROPS, /loginUserName: string;/);
	assert.match(PROPS, /loginPassword: string;/);
});

test('unsaved administration drafts stay in the focused input view and passwords are transient', () => {
	for (const name of [
		'newUserName', 'newUserEmail', 'newUserPassword', 'newUserPermissionGroups', 'newUserGroupId',
		'selectedUserId', 'editUserName', 'editUserEmail', 'editUserPassword', 'editUserPermissionGroups',
		'editUserGroupId', 'newGroupName', 'editGroupId', 'editGroupName'
	]) {
		assert.match(VIEW, new RegExp(`let ${name}(?:\\s*:[^=]+)?\\s*=\\s*\\$state`), name);
		assert.doesNotMatch(MODAL, new RegExp(`let ${name}(?:\\s*:[^=]+)?\\s*=\\s*\\$state`), name);
		assert.doesNotMatch(PAGE, new RegExp(`let ${name}(?:\\s*:[^=]+)?\\s*=\\s*\\$state`), name);
		assert.doesNotMatch(USER_OWNER, new RegExp(`let ${name}(?:\\s*:[^=]+)?\\s*=\\s*\\$state`), name);
	}
	assert.doesNotMatch(USER_OWNER, /newUserPassword|editUserPassword|loginPassword|profileNewPassword/);
	assert.doesNotMatch(USER_OWNER, /console\.(?:log|warn|error)[^\n]*(?:password|Password)/);
});

test('owner request identity and logout reset guard administration responses', () => {
	assert.match(USER_OWNER, /const requestId = \+\+userAdministrationRequestId/);
	assert.match(USER_OWNER, /requestId !== userAdministrationRequestId/);
	assert.match(USER_OWNER, /function resetForLoggedOut\(\)[\s\S]*\+\+userAdministrationRequestId/);
	assert.match(OWNER, /if \(tab === 'users'\) void userAdministration\.load\(\)/);
	assert.doesNotMatch(USER_OWNER, /deps\.loadUserSettings/);
});
