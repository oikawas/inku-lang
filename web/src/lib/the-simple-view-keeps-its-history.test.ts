// Run with: npm run test:unit  (node:test, no test dependency)
//
// The simple view keeps its history.
//
// Drawing, looking and putting away are the three things the simple UI is for,
// and the last one was missing: every optional group was off, the history group
// among them, so a simple-mode user could not reach their own past works and
// neither door of the card export could be opened. What is measured here is
// that the history group is on in simple mode, that the canvas toolbar is not
// swept away with the groups it used to hold, and the four things that were
// found to be frayed around the history while measuring that.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync, readdirSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { SIMPLE_UI_VISIBILITY, UI_VISIBILITY_KEYS, resolveUiVisibility } from './uiMode.ts';
import { derivationKindLabel } from './derivation.ts';

const PAGE = fileURLToPath(new URL('../routes/+page.svelte', import.meta.url));
const HISTORY_MANAGER = fileURLToPath(
	new URL('./components/HistoryManager.svelte', import.meta.url)
);
const CANVAS_PANEL = fileURLToPath(
	new URL('./components/CanvasPanel.svelte', import.meta.url)
);
const MANAGER_STATE = fileURLToPath(new URL('./historyManagerState.svelte.ts', import.meta.url));

const SRC = fileURLToPath(new URL('..', import.meta.url));

const read = (path: string): string => readFileSync(path, 'utf8');

/** Every product source under web/src, so "nowhere in the sources" is measured
 *  by walking them rather than by naming the files that were edited. Tests are
 *  left out: a test that names a thing to assert it is gone would answer for
 *  the thing itself. */
function sourceFiles(directory: string): string[] {
	return readdirSync(directory, { withFileTypes: true }).flatMap((entry) => {
		const path = join(directory, entry.name);
		if (entry.isDirectory()) return sourceFiles(path);
		if (/\.test\.(ts|js)$/.test(entry.name)) return [];
		return /\.(ts|js|svelte)$/.test(entry.name) ? [path] : [];
	});
}

/** The selectors of the one rule that hides groups per UI mode, on their own.
 *
 *  Cut out of the file rather than searched for across it: a `.status-bar`
 *  written anywhere else in the page must not be able to answer for this rule.
 *  The leading dot is what separates the rule from `class:ui-hide-input-modes`
 *  in the markup, which carries no dot. */
function hideRuleSelectors(source: string): string {
	const start = source.indexOf('.ui-hide-input-modes');
	assert.ok(start >= 0, 'the ui-hide rule was not found in the page');
	const brace = source.indexOf('{', start);
	const end = source.indexOf('}', brace);
	assert.match(source.slice(brace, end), /display:\s*none;/);
	return source.slice(start, brace);
}

/** The element a Svelte source encloses between `open` and its matching close,
 *  by counting the tag rather than by trusting the first close tag found. */
function elementBody(source: string, tagName: string, open: RegExp): string {
	const start = source.search(open);
	assert.ok(start >= 0, `no ${tagName} matching ${open} in the source`);
	const openTag = new RegExp(`<${tagName}\\b`, 'g');
	const closeTag = new RegExp(`</${tagName}>`, 'g');
	let depth = 0;
	let index = start;
	while (index < source.length) {
		openTag.lastIndex = index;
		closeTag.lastIndex = index;
		const next = openTag.exec(source);
		const close = closeTag.exec(source);
		assert.ok(close, `unclosed <${tagName}>`);
		if (next && next.index < close.index) {
			depth += 1;
			index = next.index + next[0].length;
		} else {
			depth -= 1;
			index = close.index + close[0].length;
			if (depth === 0) return source.slice(start, index);
		}
	}
	assert.fail(`unclosed <${tagName}>`);
}

// ── The history group in each mode ──────────────────────────────────────────

test('T-1: simple mode shows the history group and nothing else', () => {
	const visibility = resolveUiVisibility('simple', {});
	assert.deepEqual(visibility, {
		input_modes: false,
		drawing_settings: false,
		ddl_tools: false,
		detail_status: false,
		work_tools: false,
		history: true,
		auxiliary: false
	});
});

test('T-2: full mode shows all seven groups', () => {
	const visibility = resolveUiVisibility('full', {});
	assert.deepEqual(Object.values(visibility), Array(7).fill(true));
	assert.deepEqual(Object.keys(visibility).sort(), [...UI_VISIBILITY_KEYS].sort());
});

test('T-3: a custom mode is built on the simple defaults', () => {
	// What the custom mode adds is added to the simple UI, so the history the
	// simple UI now has is there too unless the user turned it off by name.
	assert.deepEqual(resolveUiVisibility('custom', { work_tools: true }), {
		input_modes: false,
		drawing_settings: false,
		ddl_tools: false,
		detail_status: false,
		work_tools: true,
		history: true,
		auxiliary: false
	});
	assert.equal(resolveUiVisibility('custom', { history: false }).history, false);
});

test('T-4: the optional groups are the same seven', () => {
	assert.deepEqual([...UI_VISIBILITY_KEYS], [
		'input_modes',
		'drawing_settings',
		'ddl_tools',
		'detail_status',
		'work_tools',
		'history',
		'auxiliary'
	]);
});

// ── The canvas toolbar survives its emptied groups ──────────────────────────

test('T-5: no UI-mode rule hides a whole row of canvas controls', () => {
	// 2026-08-16: the bar under the canvas was abolished and its buttons moved
	// into the two corner rows on the canvas. The rows hold buttons from two
	// different visibility groups now -- the hash and the provenance button
	// answer to detail_status, the rest to work_tools -- so a rule on the row
	// itself would take one group's buttons out with the other's in any custom
	// mode that keeps one and drops the other. Every button is named instead.
	const selectors = hideRuleSelectors(read(PAGE));
	assert.doesNotMatch(selectors, /:global\(\.status-bar\)/);
	assert.doesNotMatch(selectors, /:global\(\.canvas-corner-controls\)/);
	assert.doesNotMatch(selectors, /:global\(\.canvas-corner-right\)/);
	assert.doesNotMatch(selectors, /:global\(\.canvas-corner-left\)/);
	// And the two that are not work tools are named under their own group.
	assert.match(selectors, /\.ui-hide-detail-status :global\(\.canvas-hash-btn\)/);
	assert.match(selectors, /\.ui-hide-detail-status :global\(\.canvas-provenance-btn\)/);
});

test('T-6: the other UI-mode selectors are still there', () => {
	// A control: T-5 must not be satisfied by deleting the rule.
	const selectors = hideRuleSelectors(read(PAGE));
	assert.match(selectors, /\.ui-hide-work-tools :global\(\.canvas-export\)/);
	assert.match(selectors, /\.ui-hide-history :global\(\.nav-left\)/);
});

test('T-7: the canvas card door is inside the export menu, with the other two', () => {
	// This claim changed on 2026-08-16, and it changed deliberately.
	//
	// It used to read "the card button sits in the bar, not in a hidden group":
	// SVG and PNG lived in .png-wrap, which the work_tools group hides, and the
	// card button was their sibling outside it, so a simple UI kept the card
	// while losing the other two. The three were then merged into one export
	// button by request, and a merged door cannot be half hidden -- the card
	// now follows work_tools like the two it joined.
	//
	// What still holds is that the card has somewhere to leave from in every
	// mode: door one is the history manager, and the history group is on in the
	// simple UI (asserted below and in the two-doors case).
	const source = read(CANVAS_PANEL);
	const menu = elementBody(source, 'div', /<div class="export-menu"/);
	assert.match(menu, /downloadCardFromCanvas\(\)/, 'the card left the export menu');
	assert.match(menu, /onDownloadSVG\('display'\)/, 'SVG left the export menu');
	assert.match(menu, /onDownloadPNG\(/, 'PNG left the export menu');
	// One button opens all three, and it is the one the work_tools rule names.
	assert.match(source, /class="canvas-icon-btn canvas-export-btn"/);
	assert.match(hideRuleSelectors(read(PAGE)), /\.ui-hide-work-tools :global\(\.canvas-export\)/);
	assert.equal(SIMPLE_UI_VISIBILITY.history, true, 'the always-open door closed');
});

test('T-8: the history side keeps its own card button', () => {
	const source = read(HISTORY_MANAGER);
	assert.match(source, /downloadSelectedCard/);
	assert.match(source, /historyCardExport\b/);
});

// ── One source for the trash count ──────────────────────────────────────────

test('T-9: the trash count is read from one quantity', () => {
	const source = read(HISTORY_MANAGER);
	const call = source.match(/historyTrashButton\(([^)]*)\)/);
	assert.ok(call, 'the trash button label was not found');
	// Two quantities joined by || or ?? means a stale one can answer first.
	assert.doesNotMatch(call[1], /\|\||\?\?/);
	assert.match(call[1].trim(), /^[A-Za-z_$][\w$]*$/);
});

test('T-10: the works count still reads its own quantity', () => {
	// A control: T-9 must not be satisfied by making every count read the same
	// thing.
	assert.match(read(HISTORY_MANAGER), /managedHistoryTotal/);
});

// ── The dead preload path is gone, the live one stays ───────────────────────

test('T-11: the dead first-page preload is gone from the web sources', () => {
	const hits = sourceFiles(SRC).filter((path) =>
		/preloadFirstPage|preloadHistoryManagerFirstPage/.test(read(path))
	);
	assert.deepEqual(hits, []);
});

test('T-12: the live preload check is kept, with both of its callers', () => {
	// A control: preloadMatches is what stops the manager re-fetching a page it
	// already holds. Removing it with the dead path would be a regression.
	const source = read(MANAGER_STATE);
	assert.match(source, /preloadMatches\(view: HistoryManagerView/);
	const callers = source.match(/this\.preloadMatches\(/g) ?? [];
	assert.equal(callers.length, 2);
});

// ── The page-size estimate follows the CSS ──────────────────────────────────

test('T-13: both minCardWidth values follow the grid CSS', () => {
	const manager = read(HISTORY_MANAGER);
	// Read from the CSS rather than written here: a number copied into the test
	// would keep passing on the day the CSS moves again.
	const grid = manager.match(/\.history-thumb-grid\s*\{[^}]*\}/);
	assert.ok(grid, 'the thumbnail grid rule was not found');
	const minmax = grid[0].match(/minmax\((\d+)px,\s*1fr\)/);
	assert.ok(minmax, 'the grid does not use minmax(<N>px, 1fr)');
	const cssMin = Number(minmax[1]);

	const widths = [manager, read(PAGE)].map((source) => {
		const declaration = source.match(/const minCardWidth = (\d+);/);
		assert.ok(declaration, 'a minCardWidth declaration was not found');
		return Number(declaration[1]);
	});
	assert.deepEqual(widths, [cssMin, cssMin]);
});

// ── The origin of a lineage, in English ─────────────────────────────────────

test('T-14: a work with no derivation kind is the Origin', () => {
	assert.equal(derivationKindLabel(null, false), 'Origin');
	assert.equal(derivationKindLabel(undefined, false), 'Origin');
	assert.equal(derivationKindLabel(null, true), '起点');
});
