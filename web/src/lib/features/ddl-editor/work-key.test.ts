import assert from 'node:assert/strict';
import test from 'node:test';
import { ddlWorkKey } from './work-key.ts';
import { samePluginCalls } from './codemirror.ts';

test('a saved work keeps its editor key when its SVG arrives', () => {
	const result = { history_id: 'one', svg: '' };
	assert.equal(ddlWorkKey(null, result), ddlWorkKey(null, { ...result, svg: '<svg/>' }));
	const draft = { history_id: null, svg: '' };
	assert.equal(ddlWorkKey(null, draft), draft);
});

test('empty plugin arrays do not change editor configuration', () => {
	assert.equal(samePluginCalls([], []), true);
	assert.equal(samePluginCalls(undefined, []), true);
});
