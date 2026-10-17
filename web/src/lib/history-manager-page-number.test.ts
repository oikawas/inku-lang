// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { libraryPagePosition } from './libraryPagePosition.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const MANAGER = fs.readFileSync(path.join(here, 'components/HistoryManager.svelte'), 'utf8');

test('a Library opened at the newest numbers its pages as before', () => {
	assert.deepEqual(libraryPagePosition(0, 0, 36, 5182), { current: 1, total: 144 });
	assert.deepEqual(libraryPagePosition(0, 143, 36, 5182), { current: 144, total: 144 });
	assert.deepEqual(libraryPagePosition(0, 0, 36, 0), { current: 1, total: 1 });
});

test('a Library opened at the selected work counts the pages in front of it', () => {
	// Started at work 42: "Newer" moves the start to 6, then to 0.
	assert.deepEqual(libraryPagePosition(42, 0, 36, 5182), { current: 3, total: 145 });
	assert.deepEqual(libraryPagePosition(6, 0, 36, 5182), { current: 2, total: 145 });
	assert.deepEqual(libraryPagePosition(42, 1, 36, 5182), { current: 4, total: 145 });
	// The last page older than the start is the last of all.
	assert.deepEqual(libraryPagePosition(42, 142, 36, 5182), { current: 145, total: 145 });
});

test('reaching the newest realigns the pages, and only then can the total drop by one', () => {
	assert.deepEqual(libraryPagePosition(2, 0, 4, 8), { current: 2, total: 3 });
	assert.deepEqual(libraryPagePosition(0, 0, 4, 8), { current: 1, total: 2 });
});

test('both Library pagers print the position counted from the newest', () => {
	assert.match(MANAGER, /libraryPagePosition\(historyManagerStartOffset, historyManagerPage, historyManagerPageSize, managedHistoryTotal\)/);
	assert.match(MANAGER, /libraryPagePosition\(lineageStartOffset, lineageGroupPage, lineageGroupPageSize, lineageGroupTotal\)/);
	assert.doesNotMatch(MANAGER, /\(historyManagerPage \+ 1\) \+ ' \/ '|\(lineageGroupPage \+ 1\) \+ ' \/ '/);
});
