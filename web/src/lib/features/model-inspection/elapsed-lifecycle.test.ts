import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const source = readFileSync(new URL('./state.svelte.ts', import.meta.url), 'utf8');

test('target reset stops the model-inspection elapsed owner before stale finally is ignored', () => {
	const start = source.indexOf('\n\tfunction reset()');
	const end = source.indexOf('\n\treturn {', start);
	assert.ok(start >= 0 && end > start);
	const reset = source.slice(start, end);
	assert.match(reset, /modelInspectionAbortController\.abort\(\)/);
	assert.match(reset, /modelInspectionRunId \+= 1/);
	assert.match(reset, /modelInspectionElapsed\.stop\(\)/);
});
