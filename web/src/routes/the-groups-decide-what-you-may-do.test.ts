// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-12: the settings tabs are handed out by permission group.
//
// The decision is executed here, not matched in the source: a regex over
// the settings owner would stay green against an implementation that had
// quietly become a constant. The owner still asks the question at the same
// place -- canAccessSettingsTab calls straight through -- so this reaches the
// wiring the UI uses, and the last check below is what says so.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

import {
	ADMIN_ONLY_SETTINGS_TABS,
	USER_MANAGER_SETTINGS_TABS,
	canAccessSettingsTab,
	managesListedUser,
	defaultSettingsTab,
	holdsPermissionGroup
} from '../lib/permissionGroups.ts';

const ROUTES_DIR = dirname(fileURLToPath(import.meta.url));

const admin = { permission_groups: ['admins'] as const };
const plain = { permission_groups: ['users'] as const };
const leader = { permission_groups: ['leaders'] as const };

test('the admins group opens all five administrator tabs and the users tab', () => {
	assert.deepEqual(ADMIN_ONLY_SETTINGS_TABS, ['models', 'db', 'server_misc', 'logs', 'limits']);
	for (const tab of [...ADMIN_ONLY_SETTINGS_TABS, ...USER_MANAGER_SETTINGS_TABS]) {
		assert.equal(canAccessSettingsTab(tab, admin), true, tab);
	}
	assert.equal(canAccessSettingsTab('limits', admin), true, 'limits stays open to administrators');
	assert.equal(defaultSettingsTab(admin), 'models');
	assert.equal(holdsPermissionGroup(admin, 'admins'), true);
});

test('the users group opens none of them, and neither does a leader', () => {
	// The control for the check above: an implementation that answered `true`
	// unconditionally would pass that one and fail here.
	for (const tab of ADMIN_ONLY_SETTINGS_TABS) {
		assert.equal(canAccessSettingsTab(tab, plain), false, tab);
		assert.equal(canAccessSettingsTab(tab, leader), false, tab);
	}
	assert.equal(canAccessSettingsTab('limits', plain), false, 'limits stays closed to plain users');
	assert.equal(canAccessSettingsTab('limits', leader), false, 'limits stays closed to leaders');
	assert.equal(canAccessSettingsTab('plugins', plain), true, 'the shared tabs stay open');
	assert.equal(defaultSettingsTab(plain), 'plugins');
	assert.equal(holdsPermissionGroup(plain, 'admins'), false);

	// And the settings owner reaches this module rather than keeping its own copy: the
	// two checks above would pass over a decision nothing calls.
	const owner = readFileSync(join(ROUTES_DIR, '..', 'lib', 'features', 'settings', 'navigation-state.svelte.ts'), 'utf8');
	assert.match(owner, /from '\$lib\/permissionGroups'/);
	assert.match(owner, /canAccessSettingsTabFor\(tab, currentUser\)/);
});

test('a leader opens the users tab, and a plain member does not', () => {
	// The server let leaders manage the ordinary members of their own group
	// through the API and the CLI while the page kept the tab for
	// administrators; the author opened it on 2026-09-26.
	assert.deepEqual(USER_MANAGER_SETTINGS_TABS, ['users']);
	assert.equal(canAccessSettingsTab('users', leader), true);
	assert.equal(canAccessSettingsTab('users', plain), false);
});

test('the row of the leader themselves offers no edit or delete, which the server would refuse', () => {
	const self = { id: 'leader-1', permission_groups: ['leaders'] as const };
	const administrator = { id: 'admin-1', permission_groups: ['admins'] as const };
	assert.equal(managesListedUser(self, { id: 'leader-1' }), false);
	assert.equal(managesListedUser(self, { id: 'member-1' }), true);
	assert.equal(managesListedUser(administrator, { id: 'admin-1' }), true, 'administrators keep their own row');
});
