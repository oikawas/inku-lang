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
	canAccessSettingsTab,
	defaultSettingsTab,
	holdsPermissionGroup
} from '../lib/permissionGroups.ts';

const ROUTES_DIR = dirname(fileURLToPath(import.meta.url));

const admin = { permission_groups: ['admins'] as const };
const plain = { permission_groups: ['users'] as const };
const leader = { permission_groups: ['leaders'] as const };

test('the admins group opens all five administrator tabs', () => {
	assert.equal(ADMIN_ONLY_SETTINGS_TABS.length, 5);
	for (const tab of ADMIN_ONLY_SETTINGS_TABS) {
		assert.equal(canAccessSettingsTab(tab, admin), true, tab);
	}
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
	assert.equal(canAccessSettingsTab('plugins', plain), true, 'the shared tabs stay open');
	assert.equal(defaultSettingsTab(plain), 'plugins');
	assert.equal(holdsPermissionGroup(plain, 'admins'), false);

	// And the settings owner reaches this module rather than keeping its own copy: the
	// two checks above would pass over a decision nothing calls.
	const owner = readFileSync(join(ROUTES_DIR, '..', 'lib', 'features', 'settings', 'navigation-state.svelte.ts'), 'utf8');
	assert.match(owner, /from '\$lib\/permissionGroups'/);
	assert.match(owner, /canAccessSettingsTabFor\(tab, currentUser\)/);
});
