// Run with: npm run test:unit  (node:test, no test dependency)
//
// The share card gained a second door: the canvas toolbar, to the right of the
// PNG button, one press and the card is built and saved.
//
// test:unit has no DOM and no way to evaluate a .svelte file, so T-2, T-3 and
// T-4 read the product source. That is weaker than running it, but the weakness
// is in what they can see, not in what they assert: each one cuts the region it
// cares about out of the file first, so a match somewhere else in a 7,400-line
// page cannot satisfy it.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const read = (rel: string) => readFileSync(fileURLToPath(new URL(rel, import.meta.url)), 'utf8');

const JA = read('./i18n/ja.ts');
const EN = read('./i18n/en.ts');
const TYPES = read('./i18n/types.ts');
const CANVAS = read('./components/CanvasPanel.svelte');
const PAGE = read('../routes/+page.svelte');

/** The canvas toolbar only -- the row that carries SVG, PNG and now the card. */
function statusBar(source: string): string {
	const start = source.indexOf('<div class="status-bar">');
	assert.notEqual(start, -1, 'the canvas status bar was not found');
	const end = source.indexOf('{#if presentationMode', start);
	assert.notEqual(end, -1, 'the end of the canvas status bar was not found');
	return source.slice(start, end);
}

/** The card button element inside the toolbar, from its tooltip to its close. */
function cardButton(bar: string): string {
	const start = bar.indexOf('tooltipCanvasDownloadCard');
	assert.notEqual(start, -1, 'the card button is not in the canvas toolbar');
	const end = bar.indexOf('</button>', start);
	assert.notEqual(end, -1, 'the card button never closes');
	return bar.slice(start, end);
}

// ── T-1: the label ──────────────────────────────────────────────────────────

test('the label reads 共有カード / Share card, and the old one is gone', () => {
	assert.match(JA, /historyCardExport: "共有カード",/);
	assert.match(EN, /historyCardExport: "Share card",/);
	assert.doesNotMatch(JA, /historyCardExport: "カード",/);
	assert.doesNotMatch(EN, /historyCardExport: "Card",/);
});

// ── T-2: the position ───────────────────────────────────────────────────────

test('the card button sits to the right of the PNG button in the canvas toolbar', () => {
	const bar = statusBar(CANVAS);
	const png = bar.indexOf('tooltipCanvasDownloadPng');
	const card = bar.indexOf('tooltipCanvasDownloadCard');
	assert.notEqual(png, -1, 'the PNG button left the canvas toolbar');
	assert.notEqual(card, -1, 'the card button is not in the canvas toolbar');
	assert.ok(card > png, 'the card button must come after the PNG button, not before it');
});

// ── T-3: a work with no id cannot be carded ─────────────────────────────────

test('the card button is disabled when the shown work has no history id', () => {
	const button = cardButton(statusBar(CANVAS));
	const disabled = button.match(/disabled=\{([^}]*)\}/);
	assert.ok(disabled, 'the card button has no disabled expression');
	// history_id is optional on a result, and displayedHistoryItem can be null,
	// so !result alone would let a press go out with id === null.
	assert.match(disabled[1], /currentHistoryId/);
});

// ── T-4: the wiring, not just the button ────────────────────────────────────

test('the page hands the canvas a card action that reaches downloadCard', () => {
	const call = PAGE.match(/<CanvasPanel[\s\S]*?\/>/);
	assert.ok(call, 'the CanvasPanel invocation was not found');
	assert.match(call[0], /onDownloadCard=\{downloadCurrentCard\}/);
	assert.match(call[0], /currentHistoryId=\{/);

	const fn = PAGE.match(/async function downloadCurrentCard\(\)[\s\S]*?\n\t\}/);
	assert.ok(fn, 'downloadCurrentCard was not found');
	assert.match(fn[0], /downloadCard\(/);
	assert.match(fn[0], /exportSettings\.card/);
});

// ── T-5: the new string exists in all three i18n files ──────────────────────

test('the canvas card tooltip is in ja, en and types', () => {
	assert.match(JA, /tooltipCanvasDownloadCard: '.+',/);
	assert.match(EN, /tooltipCanvasDownloadCard: '.+',/);
	assert.match(TYPES, /tooltipCanvasDownloadCard: string;/);
});
