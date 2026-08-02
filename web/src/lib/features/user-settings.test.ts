// Run with: npm run test:unit  (node:test, no test dependency)
//
// The gate for the settings a feature keeps on the server.  It asserts that the
// registry really collects from and applies to every contributor, and that the
// page no longer names what a feature owns -- which is the whole point of the
// change and the thing a later edit is most likely to undo.
//
// The source half reads the files rather than importing them: the feature that
// owns a server-persisted setting declares runes, and node cannot import those
// without the Svelte compiler -- measured, not assumed.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

import {
	applyUserSettings,
	collectUserSettings,
	registerUserSettingsContributor,
	userSettingsContributorIds
} from './user-settings.ts';

const FEATURES_DIR = dirname(fileURLToPath(import.meta.url));
const PAGE = join(FEATURES_DIR, '..', '..', 'routes', '+page.svelte');
const MODEL_INSPECTION = join(FEATURES_DIR, 'model-inspection', 'state.svelte.ts');

test('the feature that keeps a setting on the server registers it', () => {
	const source = readFileSync(MODEL_INSPECTION, 'utf8');
	assert.match(source, /registerUserSettingsContributor\(/);
	assert.match(source, /model_inspection_selected_models/);
});

test('the page does not name a field a feature owns', () => {
	const page = readFileSync(PAGE, 'utf8');
	// It named it three times before: in the type it declares, where it restores
	// a user and where it saves one.
	assert.equal(page.includes('model_inspection_selected_models'), false);
});

test('every contributor is collected, and the slices are merged', () => {
	registerUserSettingsContributor({ id: 'test-a', collect: () => ({ a: 1 }), apply: () => {} });
	registerUserSettingsContributor({ id: 'test-b', collect: () => ({ b: 2 }), apply: () => {} });

	const collected = collectUserSettings();

	assert.equal(collected.a, 1);
	assert.equal(collected.b, 2);
	assert.deepEqual(
		userSettingsContributorIds().filter((id) => id.startsWith('test-')),
		['test-a', 'test-b']
	);
});

test('every contributor is handed the stored settings', () => {
	const seen: string[] = [];
	registerUserSettingsContributor({
		id: 'test-a',
		collect: () => ({}),
		apply: (settings) => seen.push(`a:${String(settings.value)}`)
	});
	registerUserSettingsContributor({
		id: 'test-b',
		collect: () => ({}),
		apply: (settings) => seen.push(`b:${String(settings.value)}`)
	});

	applyUserSettings({ value: 'stored' });

	assert.deepEqual([...seen].sort(), ['a:stored', 'b:stored']);
});

test('a user with nothing stored still reaches every contributor, so it can reset', () => {
	let applied = 0;
	registerUserSettingsContributor({
		id: 'test-a',
		collect: () => ({}),
		apply: (settings) => {
			applied += 1;
			assert.deepEqual(settings, {});
		}
	});
	registerUserSettingsContributor({ id: 'test-b', collect: () => ({}), apply: () => (applied += 1) });

	applyUserSettings(null);

	assert.equal(applied, 2);
});

test('registering the same id again replaces it, so a reload cannot double up', () => {
	registerUserSettingsContributor({ id: 'test-a', collect: () => ({ a: 'first' }), apply: () => {} });
	registerUserSettingsContributor({ id: 'test-a', collect: () => ({ a: 'second' }), apply: () => {} });
	registerUserSettingsContributor({ id: 'test-b', collect: () => ({}), apply: () => {} });

	assert.equal(collectUserSettings().a, 'second');
	assert.equal(userSettingsContributorIds().filter((id) => id === 'test-a').length, 1);
});
