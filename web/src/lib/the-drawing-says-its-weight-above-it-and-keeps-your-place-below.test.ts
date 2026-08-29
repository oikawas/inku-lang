// Run with: npm run test:unit  (node:test, no test dependency)
//
// Two things about reading a work's provenance.
//
// How heavy the drawing is was only ever said inside the drawer, so seeing it
// cost opening a panel and closing it again. It now stands in the strip above
// the canvas, beside the time the work was made -- the same measurement, said
// by the same formatter, so the two can never disagree.
//
// And the numbers there run large: a work in the reference corpus carries
// 24,446 objects, and 2.3 MB of SVG. Unseparated, those are digits to count
// with a finger. They are grouped now.
//
// The drawer also lost the reader's place every time it was closed. It is
// clipped rather than removed, so the browser would have kept the position --
// but the pane is rebuilt whenever the work on screen changes, and a shorter
// work clamps the offset it was holding. The position is remembered instead.
//
// T-95: the weight stands in the canvas strip, to the left of the created time.
// T-96: the sizes and counts are written with their thousands separated.
// T-97: the drawer comes back where it was closed, on the tab it was closed on.
// T-98: every path that closes the drawer goes through the one that remembers.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import {
	drawerScrollToRestore,
	emptyDrawerScrollMemory,
	rememberDrawerScroll
} from './drawerScroll.ts';
import { formatByteSize, formatCanvasCapacity, groupDigits } from './formatNumber.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');

const PANEL = read('./components/CanvasPanel.svelte');
const TABS = read('./components/OutputTabsContent.svelte');
const INFO = read('./features/canvas/CanvasGenerationInfo.svelte');

/** The strip above the canvas, from its opening tag to its close. */
function metaStrip(): string {
	const start = PANEL.indexOf('<div class="render-meta-strip"');
	assert.ok(start > 0, 'the canvas strip is gone');
	const end = PANEL.indexOf('</div>', PANEL.indexOf('render-meta-created'));
	return PANEL.slice(start, end);
}

// ------------------------------------------------- T-95 (it is in the strip)

test('T-95: the strip says how heavy the drawing is', () => {
	const strip = metaStrip();
	assert.match(strip, /class="render-meta-item render-meta-svg-size"/);
	assert.match(strip, /formatCanvasCapacity\(detailSvgBytes\)/);
	assert.doesNotMatch(strip, /SVG (?:\\u30b5\\u30a4\\u30ba|size)/);
});

test('T-95: it stands to the left of the time the work was made', () => {
	const strip = metaStrip();
	const size = strip.indexOf('render-meta-svg-size');
	const created = strip.indexOf('render-meta-created');
	assert.ok(size > 0 && created > 0, 'one of the two items is missing');
	assert.ok(size < created, 'the size is written after the created time, not before it');
});

test('T-95: it is the drawer\'s own measurement with a compact formatter', () => {
	// `detailSvgBytes` is the derivation the drawer reads. Measuring again here
	// would be a second count of the same drawing, and two counts drift.
	assert.equal((PANEL.match(/measureSvgWeight\(/g) ?? []).length, 1);
	assert.equal((PANEL.match(/formatCanvasCapacity\(detailSvgBytes\)/g) ?? []).length, 1);
	assert.equal((INFO.match(/formatByteSize\(detailSvgBytes\)/g) ?? []).length, 1,
		'the provenance drawer lost its detailed byte formatter');
});

// ------------------------------------------------ T-96 (thousands separated)

test('T-96: a number is written with its thousands separated', () => {
	assert.equal(groupDigits(0), '0');
	assert.equal(groupDigits(999), '999');
	assert.equal(groupDigits(1000), '1,000');
	assert.equal(groupDigits(24446), '24,446');
	assert.equal(groupDigits(1234567), '1,234,567');
	// The decimals are fixed, so a size does not change width as it changes.
	assert.equal(groupDigits(2246, 1), '2,246.0');
	assert.equal(groupDigits(2246.44, 1), '2,246.4');
});

test('T-96: a size is kilobytes above a kilobyte and bytes below one', () => {
	assert.equal(formatByteSize(null), '-');
	assert.equal(formatByteSize(undefined), '-');
	assert.equal(formatByteSize(0), '0 B');
	assert.equal(formatByteSize(300), '300 B');
	assert.equal(formatByteSize(1023), '1,023 B');
	assert.equal(formatByteSize(1024), '1.0 KB');
	// The case this came from: 2.3 MB of SVG reads as four digits, grouped.
	assert.equal(formatByteSize(2_300_000), '2,246.1 KB');
});

test('the canvas capacity is rounded to whole kilobytes with a one-kilobyte floor', () => {
	assert.equal(formatCanvasCapacity(null), '-');
	assert.equal(formatCanvasCapacity(undefined), '-');
	assert.equal(formatCanvasCapacity(0), '1 KB');
	assert.equal(formatCanvasCapacity(410), '1 KB');
	assert.equal(formatCanvasCapacity(1024), '1 KB');
	assert.equal(formatCanvasCapacity(1536), '2 KB');
	assert.equal(formatCanvasCapacity(2_300_000), '2,246 KB');
});

test('T-96: the separator does not follow the interface language', () => {
	// A drawing on screen is one drawing. Were the grouping taken from the UI
	// locale, the same size would be punctuated differently under different
	// interfaces, and a screenshot would stop being comparable.
	assert.match(read('./formatNumber.ts'), /const GROUPING_LOCALE = 'en-US';/);
	assert.doesNotMatch(read('./formatNumber.ts'), /getLang|isJapanese/);
});

test('T-96: the drawer writes its sizes, counts and tokens the same way', () => {
	assert.match(INFO, /\{detailSvgWeight \? groupDigits\(detailSvgWeight\.objects\) : '-'\}/);
	assert.match(INFO, /\{detailSvgWeight \? groupDigits\(detailSvgWeight\.points\) : '-'\}/);
	assert.match(INFO, /\{detailTokensIn == null \? '-' : groupDigits\(detailTokensIn\)\}/);
	assert.match(INFO, /\{detailTokensOut == null \? '-' : groupDigits\(detailTokensOut\)\}/);
	// A dash, never a zero: grouping a number that was never recorded would
	// print `0` and claim the work used no tokens.
	assert.doesNotMatch(INFO, /groupDigits\(detailTokensIn \?\? 0\)/);
});

// ------------------------------------------- T-97 (it keeps the reader's place)

test('T-97: closing remembers where the reader was, per tab', () => {
	let memory = emptyDrawerScrollMemory();
	assert.equal(drawerScrollToRestore(memory, 'details'), 0);

	memory = rememberDrawerScroll(memory, 'details', 640);
	assert.equal(drawerScrollToRestore(memory, 'details'), 640);
	// The other tabs are untouched: the drawer remembers which tab was open
	// too, and a depth from one list means nothing in another.
	assert.equal(drawerScrollToRestore(memory, 'prompts'), 0);
	assert.equal(drawerScrollToRestore(memory, 'score'), 0);

	memory = rememberDrawerScroll(memory, 'score', 120);
	assert.equal(drawerScrollToRestore(memory, 'details'), 640);
	assert.equal(drawerScrollToRestore(memory, 'score'), 120);
});

test('T-97: an offset that is not a position is the top', () => {
	// Rubber-band scrolling reports a negative offset, and an element that is
	// not on screen can report NaN. Neither is a place to come back to.
	const memory = emptyDrawerScrollMemory();
	assert.equal(drawerScrollToRestore(rememberDrawerScroll(memory, 'details', -80), 'details'), 0);
	assert.equal(drawerScrollToRestore(rememberDrawerScroll(memory, 'details', NaN), 'details'), 0);
});

test('T-97: the pane that scrolls is bound in all three tabs', () => {
	// Each tab scrolls a different element, and two of them belong to
	// OutputTabsContent. Without the binding the drawer would remember the
	// details list and silently forget the other two.
	assert.match(INFO, /class="generation-details" bind:this=\{detailsScrollEl\}/);
	assert.match(INFO, /bind:scrollEl=\{tabsScrollEl\}/);
	assert.match(TABS, /class="prompt-section" bind:this=\{scrollEl\}/);
	assert.match(TABS, /class="score-view" bind:this=\{scrollEl\}/);
	// And the drawer asks for the right one for the tab it is on.
	assert.match(PANEL, /generationInfoTab === 'details' \? detailsScrollEl : tabsScrollEl/);
});

// ------------------------------------------ T-98 (no path forgets to remember)

test('T-98: every path that closes the drawer goes through the one that remembers', () => {
	// There are four: the close button, the toggle, Escape, and a press
	// outside. A path that set the flag directly would close without saving,
	// and it would be the quiet one -- three of four working looks like it
	// works.
	const closings = PANEL.match(/generationInfoOpen = false/g) ?? [];
	assert.equal(closings.length, 1, `${closings.length} places close the drawer directly`);
	const fn = PANEL.slice(PANEL.indexOf('function closeGenerationInfo'), PANEL.indexOf('function openGenerationInfo'));
	assert.match(fn, /generationInfoOpen = false/, 'the one closing is not inside closeGenerationInfo');
	assert.match(fn, /rememberDrawerScroll\(drawerScrollMemory, generationInfoTab, pane\.scrollTop\)/);
	// The four call sites.
	assert.equal((PANEL.match(/closeGenerationInfo\b/g) ?? []).length, 5, 'a closing path was added or lost');
});

test('T-98: opening restores after the pane is on screen, not before', () => {
	const fn = PANEL.slice(PANEL.indexOf('function openGenerationInfo'), PANEL.indexOf('function openGenerationInfo') + 700);
	assert.match(fn, /generationInfoOpen = true/);
	// Setting scrollTop in the same tick sets it against the height the pane
	// had before it was rebuilt, and the browser clamps it to that.
	assert.match(fn, /tick\(\)\.then/);
	assert.match(fn, /pane\.scrollTop = drawerScrollToRestore\(drawerScrollMemory, generationInfoTab\)/);
});
