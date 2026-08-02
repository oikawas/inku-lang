// Run with: npm run test:unit  (node:test, no test dependency)
//
// The gate for the start-up load block.  It asserts two things: that the
// registry really calls every setting it was given (and in a way that keeps the
// abort semantics the hand-written block had), and that every settings module
// in the tree is actually registered.
//
// The second half reads the source rather than importing it: the settings
// modules declare runes, and node cannot import those without the Svelte
// compiler -- measured, not assumed.  A registration deleted from any of them
// turns this file red.
import assert from 'node:assert/strict';
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

import {
	loadPersistedSettings,
	persistedSettingIds,
	registerPersistedSetting
} from './persisted-settings.ts';

const FEATURES_DIR = dirname(fileURLToPath(import.meta.url));

function featureModules(): string[] {
	const found: string[] = [];
	const walk = (dir: string) => {
		for (const entry of readdirSync(dir, { withFileTypes: true })) {
			const path = join(dir, entry.name);
			if (entry.isDirectory()) walk(path);
			else if (entry.name.endsWith('.svelte.ts')) found.push(path);
		}
	};
	walk(FEATURES_DIR);
	return found.sort();
}

test('a module that restores itself from storage is registered to be restored', () => {
	const declaresLoad: string[] = [];
	const registers: string[] = [];
	for (const path of featureModules()) {
		const source = readFileSync(path, 'utf8');
		// The shape every settings module uses: `load = () => { ... }`.
		if (/\bload\s*=\s*\(\)\s*=>/.test(source)) declaresLoad.push(path);
		if (source.includes('registerPersistedSetting(')) registers.push(path);
	}
	assert.notEqual(declaresLoad.length, 0, 'no settings module was found at all');
	assert.deepEqual(registers, declaresLoad);
});

test('every registered setting is restored, and only once', () => {
	const restored: string[] = [];
	registerPersistedSetting({ id: 'test-a', load: () => restored.push('a') });
	registerPersistedSetting({ id: 'test-b', load: () => restored.push('b') });

	loadPersistedSettings();

	assert.deepEqual([...restored].sort(), ['a', 'b']);
	assert.deepEqual(
		persistedSettingIds().filter((id) => id.startsWith('test-')),
		['test-a', 'test-b']
	);
});

test('a latch registered as afterLoad runs only once the whole block has', () => {
	const order: string[] = [];
	registerPersistedSetting({ id: 'test-a', load: () => order.push('load-a') });
	registerPersistedSetting({
		id: 'test-b',
		load: () => order.push('load-b'),
		afterLoad: () => order.push('after-b')
	});

	loadPersistedSettings();

	assert.equal(order.at(-1), 'after-b');
	assert.equal(order.filter((step) => step === 'after-b').length, 1);
});

test('a storage failure aborts the block, exactly as the hand-written one did', () => {
	const restored: string[] = [];
	registerPersistedSetting({
		id: 'test-a',
		load: () => {
			throw new Error('quota');
		}
	});
	registerPersistedSetting({
		id: 'test-b',
		load: () => restored.push('b'),
		afterLoad: () => restored.push('after-b')
	});

	assert.throws(() => loadPersistedSettings(), /quota/);
	assert.deepEqual(restored, []);
});

test('registering the same id again replaces it, so a reload cannot double up', () => {
	let calls = 0;
	registerPersistedSetting({ id: 'test-a', load: () => (calls += 1) });
	registerPersistedSetting({ id: 'test-a', load: () => (calls += 1) });
	registerPersistedSetting({ id: 'test-b', load: () => {} });

	loadPersistedSettings();

	assert.equal(calls, 1);
	assert.equal(persistedSettingIds().filter((id) => id === 'test-a').length, 1);
});
