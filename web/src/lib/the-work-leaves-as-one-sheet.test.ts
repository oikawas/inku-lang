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
// (2) the card did not become a fourth essential of the simple UI. The
//     essentials are the description input, the drawing and the canvas; every
//     optional group is a key in SIMPLE_UI_VISIBILITY, all of them off. The
//     card lives in the history group, which is one of those.
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

// ── T-10 (2): the simple UI gained nothing ──────────────────────────────────

test('the card did not become an essential of the simple UI', () => {
	// The optional groups, and their state in simple mode. A new key here, or
	// any of them turned on, would mean the simple UI grew.
	assert.deepEqual([...UI_VISIBILITY_KEYS], [
		'input_modes',
		'drawing_settings',
		'ddl_tools',
		'detail_status',
		'work_tools',
		'history',
		'auxiliary'
	]);
	assert.deepEqual(Object.values(SIMPLE_UI_VISIBILITY), Array(7).fill(false));

	// And the card export itself sits in the history group rather than beside
	// the description input: it is in the component the history group renders.
	const source = readFileSync(HISTORY_MANAGER, 'utf8');
	assert.match(source, /downloadSelectedCard/);
	assert.match(source, /historyCardExport\b/);
});
