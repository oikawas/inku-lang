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
const ARTWORK = read('./features/canvas/CanvasArtworkWorkspace.svelte');
const PAGE = read('../routes/+page.svelte');

const MENU = read('./components/SavedWorkExportMenu.svelte');

/** The single-work entries of the one export menu: SVG, PNG and the card. */
function exportMenu(): string {
	const start = MENU.indexOf('{#if single && onDownloadSVG && onDownloadPNG}');
	assert.notEqual(start, -1, 'the export menu has no single-work entries');
	const end = MENU.indexOf('{#if onDownloadDdl}', start);
	assert.notEqual(end, -1, 'the end of the single-work entries was not found');
	return MENU.slice(start, end);
}

/** The simple UI's export button, which calls the card alone. */
function cardOnlyButton(): string {
	const start = ARTWORK.indexOf('{#if exportCardOnly}');
	assert.notEqual(start, -1, 'the simple UI export branch is gone');
	const end = ARTWORK.indexOf('{:else if savedWorkExport}', start);
	assert.notEqual(end, -1, 'the simple UI export branch never ends');
	return ARTWORK.slice(start, end);
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
	// Since 2026-09-27 the canvas has one export menu, the saved work's.
	const menu = exportMenu();
	const png = menu.indexOf('onDownloadPNG');
	const card = menu.indexOf('onDownloadCard');
	assert.notEqual(png, -1, 'the PNG entry left the export menu');
	assert.notEqual(card, -1, 'the card entry is not in the export menu');
	assert.ok(card > png, 'the card must come after PNG, not before it');
	// And SVG before both, so the merge kept the order the three buttons had.
	const svg = menu.indexOf('onDownloadSVG');
	assert.notEqual(svg, -1, 'the SVG entries left the export menu');
	assert.ok(svg < png, 'SVG must come before PNG');
});

// ── T-3: a work with no id cannot be carded ─────────────────────────────────

test('the card button is disabled when the shown work has no history id', () => {
	// The menu is only handed over for a saved work, so its card entry always
	// has an id; the simple UI's button, which calls the card directly, keeps
	// its own test for that.
	assert.match(read('./components/CanvasPanel.svelte'), /savedWorkExport=\{currentHistoryId && /);
	const disabled = cardOnlyButton().match(/disabled=\{([^}]*)\}/);
	assert.ok(disabled, 'the card button has no disabled expression');
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
