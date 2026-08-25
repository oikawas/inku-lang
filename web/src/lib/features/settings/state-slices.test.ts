import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string): string => {
	try { return readFileSync(new URL(path, import.meta.url), 'utf8'); }
	catch { return ''; }
};

test('T-1001/T-1005: the Settings aggregate constructs four route-instance owners once', () => {
	const aggregate = read('./state.svelte.ts');

	for (const factory of [
		'createSettingsNavigation',
		'createServerAdministration',
		'createModelAdministration',
		'createUserAdministration'
	]) {
		assert.equal((aggregate.match(new RegExp(`${factory}\\(`, 'g')) ?? []).length, 1, factory);
	}
	assert.doesNotMatch(aggregate, /\$state\(/);
	assert.match(aggregate, /resetForLoggedOut\(\) \{[\s\S]*userAdministration\.resetForLoggedOut\(\)[\s\S]*serverAdministration\.resetForLoggedOut\(\)/);
});

test('T-1001/T-1003: each Settings responsibility has one focused owner', () => {
	const navigation = read('./navigation-state.svelte.ts');
	const server = read('./server-administration.svelte.ts');
	const model = read('./model-administration.svelte.ts');
	const user = read('./user-administration.svelte.ts');

	assert.match(navigation, /let settingsOpen = \$state/);
	assert.match(navigation, /SETTINGS_DETAIL_KEY/);
	assert.match(server, /let settingsStatus = \$state/);
	assert.match(server, /\/api\/plugins/);
	assert.match(model, /let modelSettings = \$state/);
	assert.match(model, /\/api\/settings\/models/);
	assert.match(user, /let users = \$state/);
	assert.match(user, /\/api\/user-groups/);
	assert.doesNotMatch(navigation, /\/api\/(?:plugins|users|user-groups)|\/api\/settings\/(?:status|models)/);
	assert.doesNotMatch(server, /\/api\/settings\/models|\/api\/users|\/api\/user-groups/);
	assert.doesNotMatch(model, /\/api\/plugins|\/api\/users|\/api\/user-groups/);
	assert.doesNotMatch(user, /\/api\/plugins|\/api\/settings\/(?:status|models)/);
});

test('I-245: limits is a persisted content tab through the existing guarded path', () => {
	const navigation = read('./navigation-state.svelte.ts');

	assert.match(navigation, /function isSettingsContentTab[\s\S]*tab === 'limits'/);
	assert.match(navigation, /function selectSettingsTab[\s\S]*updateUserSettingsTab\(tab\)/);
	assert.match(navigation, /function openSettings[\s\S]*isSettingsContentTab\(saved\)[\s\S]*canAccessSettingsTab\(candidate\)/);
});
