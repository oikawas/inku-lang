// Run with: npm run test:unit  (node:test, no test dependency)
//
// The share card gained a second door: the canvas, to the right of the PNG
// button, one press and the card is built and saved.
//
// 2026-08-16: the toolbar under the canvas was abolished and its three ways out
// -- SVG, PNG, the card -- became one export button standing on the canvas
// itself. The card is still the last of the three, so the order these cases
// pin is unchanged; what moved is where to look for it.
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

/** The export menu only -- the list that carries SVG, PNG and the card. */
function exportMenu(source: string): string {
	const start = source.indexOf('<div class="export-menu"');
	assert.notEqual(start, -1, 'the canvas export menu was not found');
	const end = source.indexOf('<Tooltip placement="top-left" text={t().tooltipCanvasPresentation}>', start);
	assert.notEqual(end, -1, 'the end of the canvas export menu was not found');
	return source.slice(start, end);
}

/** The card entry inside the menu, from its own disabled test to its close. */
function cardButton(menu: string): string {
	const start = menu.indexOf('cardExportBusy ? t().cardExportBusy');
	assert.notEqual(start, -1, 'the card entry is not in the export menu');
	const open = menu.lastIndexOf('<button', start);
	assert.notEqual(open, -1, 'the card entry has no button around it');
	const end = menu.indexOf('</button>', start);
	assert.notEqual(end, -1, 'the card entry never closes');
	return menu.slice(open, end);
}

// ── T-1: the label ──────────────────────────────────────────────────────────

test('the label reads 共有カード / Share card, and the old one is gone', () => {
	assert.match(JA, /historyCardExport: "共有カード",/);
	assert.match(EN, /historyCardExport: "Share card",/);
	assert.doesNotMatch(JA, /historyCardExport: "カード",/);
	assert.doesNotMatch(EN, /historyCardExport: "Card",/);
});

// ── T-2: the position ───────────────────────────────────────────────────────

test('the card is the last of the three ways out, after PNG', () => {
	const menu = exportMenu(CANVAS);
	const png = menu.indexOf('onDownloadPNG');
	const card = menu.indexOf('downloadCardFromCanvas');
	assert.notEqual(png, -1, 'the PNG entry left the canvas export menu');
	assert.notEqual(card, -1, 'the card entry is not in the canvas export menu');
	assert.ok(card > png, 'the card must come after PNG, not before it');
	// And SVG before both, so the merge kept the order the three buttons had.
	const svg = menu.indexOf('onDownloadSVG');
	assert.notEqual(svg, -1, 'the SVG entries left the canvas export menu');
	assert.ok(svg < png, 'SVG must come before PNG');
});

// ── T-3: a work with no id cannot be carded ─────────────────────────────────

test('the card button is disabled when the shown work has no history id', () => {
	const button = cardButton(exportMenu(CANVAS));
	const disabled = button.match(/disabled=\{([^}]*)\}/);
	assert.ok(disabled, 'the card button has no disabled expression');
	// history_id is optional on a result, and displayedHistoryItem can be null,
	// so the export button's own `!result` would let a press go out with
	// id === null. The entry keeps its own test for that.
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
