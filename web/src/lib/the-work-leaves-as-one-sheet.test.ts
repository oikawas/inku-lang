// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-10, the web side of the card. Two different things:
//
// (1) the page shape and the seal chosen in the settings reach the request body
//     unchanged. The server can already leave the seal off -- that is measured
//     server-side -- but a client that sends two constants would pass that test
//     and still make the setting do nothing. This drives the layer that builds
//     the body, so a constant cannot hide behind a correct-looking picture.
//
// (2) the card has two doors and neither is closed by a UI mode. One is on the
//     canvas status bar, the other in the history manager; a work can be taken
//     out as one sheet from whichever surface the user is looking at.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
	DEFAULT_CARD_EXPORT_SETTINGS,
	cardExportRequestBody,
	normalizeCardExportSettings
} from './cardExportRequest.ts';
import { SIMPLE_UI_VISIBILITY, UI_VISIBILITY_KEYS } from './uiMode.ts';

const HISTORY_MANAGER = fileURLToPath(
	new URL('./components/HistoryManager.svelte', import.meta.url)
);
const CANVAS_PANEL = fileURLToPath(
	new URL('./components/CanvasPanel.svelte', import.meta.url)
);
const PAGE = fileURLToPath(new URL('../routes/+page.svelte', import.meta.url));

/** The selectors of the one rule that hides groups per UI mode, on their own.
 *
 *  Read as a rule rather than as a file: a `.status-bar` written anywhere else
 *  in the page must not be able to answer for this one. */
function hideRuleSelectors(source: string): string {
	// The dot is what separates the rule from `class:ui-hide-input-modes` in the
	// markup, which carries no dot.
	const start = source.indexOf('.ui-hide-input-modes');
	assert.ok(start >= 0, 'the ui-hide rule was not found in the page');
	const brace = source.indexOf('{', start);
	const end = source.indexOf('}', brace);
	assert.match(source.slice(brace, end), /display:\s*none;/);
	return source.slice(start, brace);
}

// ── T-10 (1): the choices reach the wire ────────────────────────────────────

test('the default card is square with the seal on', () => {
	assert.deepEqual(DEFAULT_CARD_EXPORT_SETTINGS, { layout: 'square', seal: true });
	assert.deepEqual(cardExportRequestBody('work-1', DEFAULT_CARD_EXPORT_SETTINGS), {
		id: 'work-1',
		layout: 'square',
		seal: true
	});
});

test('every combination of page shape and seal is carried, not a constant', () => {
	for (const layout of ['square', 'portrait'] as const) {
		for (const seal of [true, false]) {
			assert.deepEqual(cardExportRequestBody('work-2', { layout, seal }), {
				id: 'work-2',
				layout,
				seal
			});
		}
	}
	// A stored setting from before the seal existed keeps the default rather
	// than reading as off.
	assert.equal(normalizeCardExportSettings({ layout: 'portrait' }).seal, true);
	assert.equal(normalizeCardExportSettings({ layout: 'portrait', seal: false }).seal, false);
});

// ── T-10 (2): the card has two doors, and no UI mode closes them ────────────

test('the card has two doors, and one of them is open in every mode', () => {
	// The optional groups. A new key here would mean the UI grew a group the
	// modes do not know about.
	assert.deepEqual([...UI_VISIBILITY_KEYS], [
		'input_modes',
		'drawing_settings',
		'ddl_tools',
		'detail_status',
		'work_tools',
		'history',
		'auxiliary'
	]);

	// Door one lives in the history manager, which the simple UI now shows: the
	// group is on, so the door is reachable from every mode.
	const source = readFileSync(HISTORY_MANAGER, 'utf8');
	assert.match(source, /downloadSelectedCard/);
	assert.match(source, /historyCardExport\b/);
	assert.equal(SIMPLE_UI_VISIBILITY.history, true);

	// Door two is on the canvas. It used to be a button of its own beside SVG
	// and PNG, deliberately outside the .png-wrap the work_tools group hides,
	// so a simple UI kept the card while losing the other two ways out.
	//
	// On 2026-08-16 the three were merged into one export button by request.
	// A merged door cannot be half hidden, so door two now follows work_tools
	// with the two it joined -- which is why this case no longer claims that
	// neither door is hidden. Door one carries the promise on its own: the
	// history group is on in the simple UI, so the card is always reachable.
	const canvas = readFileSync(CANVAS_PANEL, 'utf8');
	assert.match(canvas, /downloadCardFromCanvas\(\)/);
	const page = readFileSync(PAGE, 'utf8');
	// The bar that used to hold it is gone, so no rule may name it either.
	assert.doesNotMatch(hideRuleSelectors(page), /:global\(\.status-bar\)/);
	assert.doesNotMatch(canvas, /class="status-bar"/);
});
