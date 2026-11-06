import assert from 'node:assert/strict';
import { test } from 'node:test';
import { libraryArrowDestination as destination } from './arrow-navigation.ts';

test('moves in four directions in the displayed grid', () => {
	assert.deepEqual(destination(4, 9, 3, 'ArrowLeft'), { kind: 'index', index: 3 });
	assert.deepEqual(destination(4, 9, 3, 'ArrowRight'), { kind: 'index', index: 5 });
	assert.deepEqual(destination(4, 9, 3, 'ArrowUp'), { kind: 'index', index: 1 });
	assert.deepEqual(destination(4, 9, 3, 'ArrowDown'), { kind: 'index', index: 7 });
});

test('down reaches a short last row, then continues to the next page', () => {
	assert.deepEqual(destination(5, 7, 3, 'ArrowDown'), { kind: 'index', index: 6 });
	assert.deepEqual(destination(6, 7, 3, 'ArrowDown'), { kind: 'next-page' });
});

test('all four page edges and a single-column list', () => {
	assert.deepEqual(destination(0, 7, 3, 'ArrowLeft'), { kind: 'previous-page' });
	assert.deepEqual(destination(2, 7, 3, 'ArrowUp'), { kind: 'previous-page' });
	assert.deepEqual(destination(6, 7, 3, 'ArrowRight'), { kind: 'next-page' });
	assert.deepEqual(destination(6, 7, 3, 'ArrowDown'), { kind: 'next-page' });
	assert.deepEqual(destination(1, 3, 1, 'ArrowUp'), { kind: 'index', index: 0 });
	assert.deepEqual(destination(1, 3, 1, 'ArrowDown'), { kind: 'index', index: 2 });
	assert.deepEqual(destination(0, 0, 1, 'ArrowDown'), { kind: 'none' });
	assert.deepEqual(destination(0, 3, 1, 'Enter'), { kind: 'none' });
});
