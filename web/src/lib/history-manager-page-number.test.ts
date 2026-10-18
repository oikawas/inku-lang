// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { libraryPagePosition, libraryRelativePage } from './libraryPagePosition.ts';

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

test('a typed page number asks for the page that number names', () => {
	assert.equal(libraryRelativePage(1, 0, 36, 5182), 0);
	assert.equal(libraryRelativePage(144, 0, 36, 5182), 143);
	// Opened at work 42, shown as 3 / 145.
	assert.equal(libraryRelativePage(3, 42, 36, 5182), 0);
	assert.equal(libraryRelativePage(2, 42, 36, 5182), -1, 'one press of Newer: the start moves to 6');
	assert.equal(libraryRelativePage(1, 42, 36, 5182), -2, 'the newest: the start moves to 0');
	assert.equal(libraryRelativePage(145, 42, 36, 5182), 142);
	assert.equal(libraryRelativePage(0, 42, 36, 5182), -2, 'below the first lands on the first');
	assert.equal(libraryRelativePage(999, 42, 36, 5182), 142, 'past the last lands on the last');
});

test('both Library pagers take a typed page, and the search is drawn like the strip', () => {
	assert.match(MANAGER, /<LibraryPageInput current=\{managerPosition\.current\} total=\{managerPosition\.total\} onJump=\{\(page\) => onSetPage\(libraryRelativePage\(page, historyManagerStartOffset, historyManagerPageSize, managedHistoryTotal\)\)\} \/>/);
	assert.match(MANAGER, /<LibraryPageInput current=\{lineagePosition\.current\} total=\{lineagePosition\.total\} onJump=\{\(page\) => setLineageGroupPage\(libraryRelativePage\(page, lineageStartOffset, lineageGroupPageSize, lineageGroupTotal\)\)\} \/>/);
	// A typed page may lie before the start from any page, not only from the start's own.
	assert.match(MANAGER, /if \(page < 0 && lineageStartOffset > 0\) \{/);
	assert.doesNotMatch(MANAGER, /<label for="library-history-search">/);
	assert.match(MANAGER, /placeholder=\{t\(\)\.historySearchPlaceholder\}/);
	assert.match(MANAGER, /\.history-search-input \{[^}]*border-radius: var\(--btn-sm-radius\);/);
});

test('a page field that does not move puts the page shown back into itself', () => {
	const field = fs.readFileSync(path.join(here, 'components/LibraryPageInput.svelte'), 'utf8');
	assert.match(field, /function restore\(\): void \{\s*editing = false;\s*if \(inputEl\) inputEl\.value = String\(current\);\s*\}/);
	// Both ways out that do not move: Enter on the same or no number, and Escape.
	assert.match(field, /restore\(\);\s*\/\/ Not a number: the page shown stays/);
	assert.match(field, /event\.key === 'Escape'\) \{[\s\S]*?restore\(\);/);
});
