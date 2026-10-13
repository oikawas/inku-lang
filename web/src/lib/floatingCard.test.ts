// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/floatingCard.test.ts
//
// Where a model card opens beside its model. The card is fixed to the window, so
// what can still go wrong is the place: it has to stay inside the window, and a
// model low in a list must open its card upward (the model selection dialog cut
// such a card at its bottom edge, 2026-10-13).
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { floatingCardPosition } from './floatingCard';

const window = { width: 1400, height: 858 };
const card = { width: 340, height: 220 };

test('a card that fits below its model opens below it', () => {
	assert.deepEqual(floatingCardPosition({ top: 300, bottom: 334, left: 382 }, card, window), { top: 340, left: 382 });
});

test('a model near the bottom opens its card above it, not past the edge', () => {
	assert.deepEqual(floatingCardPosition({ top: 700, bottom: 734, left: 382 }, card, window), { top: 474, left: 382 });
});

test('a card that fits on neither side stays inside the window', () => {
	const tall = { width: 340, height: 600 };
	assert.deepEqual(floatingCardPosition({ top: 400, bottom: 434, left: 1200 }, tall, window), { top: 250, left: 1052 });
});
