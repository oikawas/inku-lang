import assert from 'node:assert/strict';
import { test } from 'node:test';
import { libraryArrowDestination as destination, libraryPageTargetIndex } from './arrow-navigation.ts';

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

test('finds the target position on the newly loaded page', () => {
	// The prior page overlaps a page anchored at offset 5.
	assert.equal(libraryPageTargetIndex(5 - 1, 0, 20), 4);
	assert.equal(libraryPageTargetIndex(40 - 1, 20, 20), 19);
	assert.equal(libraryPageTargetIndex(20 + 20, 40, 20), 0);
	assert.equal(libraryPageTargetIndex(99, 40, 10), 9);
	assert.equal(libraryPageTargetIndex(0, 20, 20), 0);
	assert.equal(libraryPageTargetIndex(0, 0, 0), null);
});
