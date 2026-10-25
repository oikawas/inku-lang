// ← and → on a picture in the history strip open the next work newer or older,
// through the same per-work move as the canvas buttons, which crosses pages
// (historyNavTarget, driven in the-navigation-buttons-agree-on-which-way-is-newer).
// Wiring is read from the source: node --test cannot evaluate a .svelte file.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { historyNavTarget } from './historyNavigation';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const strip = read('./components/HistoryStrip.svelte');
const page = read('../routes/+page.svelte');

test('the strip sends ← newer and → older, and the page opens them through the per-work move', () => {
	const handler = strip.slice(strip.indexOf('function handleThumbKeydown'), strip.indexOf('let thumbStrip'));
	assert.match(handler, /event\.key === 'ArrowLeft' \? onNewerWork : onOlderWork/);
	assert.match(handler, /if \(interactionLocked\) return;\s*\/\/[^\n]*\n\s*void moveByKey/);
	const call = page.slice(page.indexOf('<HistoryStrip'), page.indexOf('/>', page.indexOf('<HistoryStrip')));
	assert.match(call, /onNewerWork=\{gotoNext\}/);
	assert.match(call, /onOlderWork=\{gotoPrev\}/);
	assert.match(page, /async function gotoNext\(\) \{\s*const item = await history\.move\('newer'\);/);
	assert.match(page, /async function gotoPrev\(\) \{\s*const item = await history\.move\('older'\);/);
});

test('the focus follows the opened work, which may sit on another page', () => {
	const move = strip.slice(strip.indexOf('async function moveByKey'), strip.indexOf('</script>'));
	assert.match(move, /await move\(\);\s*await tick\(\);/);
	assert.match(move, /querySelector<HTMLElement>\('\.thumb\.current'\)/);
	assert.match(move, /current\?\.focus\(\)/);
});

test('at either end of a page the move fetches the neighbouring page', () => {
	// The last picture of the first page steps to the first of the second.
	assert.deepEqual(historyNavTarget({ cursor: 9, offset: 0, total: 25, windowSize: 10 }, 'older'), { offset: 10, select: 0 });
	// The first picture of the second page steps back to the last of the first.
	assert.deepEqual(historyNavTarget({ cursor: 0, offset: 10, total: 25, windowSize: 10 }, 'newer'), { offset: 0, select: 9 });
	// The newest and the oldest work go no further.
	assert.equal(historyNavTarget({ cursor: 0, offset: 0, total: 25, windowSize: 10 }, 'newer'), null);
	assert.equal(historyNavTarget({ cursor: 4, offset: 20, total: 25, windowSize: 10 }, 'older'), null);
});
