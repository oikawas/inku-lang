import assert from 'node:assert/strict';
import { test } from 'node:test';
import { selectionOrder } from './selection-order.ts';

test('selection numbers follow click order and close the gap after deselection', () => {
	let ids = ['b', 'a', 'c'];
	assert.deepEqual(['a', 'b', 'c', 'd'].map((id) => selectionOrder(ids, id)), [2, 1, 3, 0]);
	ids = ids.filter((id) => id !== 'a');
	assert.deepEqual(['b', 'a', 'c'].map((id) => selectionOrder(ids, id)), [1, 0, 2]);
});
