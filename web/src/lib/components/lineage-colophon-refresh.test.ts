import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';

test('opening the colophon reads it once again and a closed dialog does not read it', () => {
	const source = readFileSync(new URL('./LineagePanel.svelte', import.meta.url), 'utf8');
	assert.match(source, /if \(okugakiOpen && target\) void untrack\(\(\) => loadOkugaki\(true\)\)/);
	assert.equal((source.match(/loadOkugaki\(true\)/g) ?? []).length, 1);
	assert.match(source, /okugakiOpen = true;/);
});
