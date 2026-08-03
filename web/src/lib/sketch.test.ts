// Run with: npm run test:unit  (node:test, no test dependency)
//
// 写生 (Stage 0.5) acceptance, web side. T-9 (the grain is a real option, wired
// from both places that can start a draw) and T-10 (the genealogy edge).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { submitDerivationKind } from './derivation.ts';
import {
	DEFAULT_SKETCH_MODE,
	normalizeSketchGrain,
	sketchGrainOf,
	sketchModeOf,
	SKETCH_MODES
} from './sketch.ts';

// ---------------------------------------------------------------- T-9 (grain)

test('T-9: a draw with no grain chosen uses fine', () => {
	assert.equal(DEFAULT_SKETCH_MODE, 'fine');
	assert.equal(sketchGrainOf(DEFAULT_SKETCH_MODE), 'fine');
});

test('T-9: the control offers off as well as both grains', () => {
	assert.deepEqual(SKETCH_MODES, ['off', 'fine', 'coarse']);
	// Off must send no grain at all: a grain with the layer off would record a
	// setting the work never used.
	assert.equal(sketchGrainOf('off'), null);
});

test('T-9: a work saved before the layer existed reads as off, not as fine', () => {
	assert.equal(normalizeSketchGrain(undefined), null);
	assert.equal(normalizeSketchGrain(null), null);
	assert.equal(normalizeSketchGrain('segmented'), null);
	assert.equal(sketchModeOf(undefined), 'off');
	assert.equal(sketchModeOf('coarse'), 'coarse');
});

test('T-9: the grain is selectable from the work menu, not only from a first draw', () => {
	// The work menu is the second place a draw can start. Wiring only the
	// describe tab passes every other gate here while the menu silently paints
	// at the default -- one call site passing while the other defaults is
	// exactly the shape that hides behind a single site.
	const panel = readFileSync(new URL('./components/LineagePanel.svelte', import.meta.url), 'utf8');
	assert.match(panel, /写生の区切りを変える/);
	assert.match(panel, /onDrawSketchGrain\(activeSketchNode, sketchGrainChoice/);

	const page = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf8');
	// The menu path must ask for a specific grain and must NOT hand over stored
	// prose: the grain is what changed, so the prose has to be written again.
	const handler = page.slice(
		page.indexOf('async function drawLineageSketchGrain'),
		page.indexOf('async function drawLineageDdlEdit')
	);
	assert.ok(handler.length > 0, 'the work-menu handler is missing');
	assert.match(handler, /sketchMode: grain/);
	assert.match(handler, /derivationKind: 'sketch_grain_change'/);
	assert.doesNotMatch(handler, /sketchText/);
});

test('T-9: the describe tab sends the chosen grain, and replays stored prose only when nothing moved', () => {
	const page = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf8');
	assert.match(page, /sketch:\s*resolvedSketchMode !== 'off'/);
	assert.match(page, /sketch_grain: resolvedSketchGrain/);
	assert.match(page, /!submitTextChanged && !submitGrainChanged \? sketchText : null/);
});

// ----------------------------------------------------------------- T-10 (edge)

test('T-10: a different grain writes sketch_grain_change', () => {
	assert.equal(
		submitDerivationKind({ hasParent: true, canvasAspectChanged: false, textChanged: false, grainChanged: true }),
		'sketch_grain_change'
	);
});

test('T-10: the same grain stays a replay', () => {
	assert.equal(
		submitDerivationKind({ hasParent: true, canvasAspectChanged: false, textChanged: false, grainChanged: false }),
		'replay'
	);
});

test('T-10: a changed description is a description edit even when the grain moved too', () => {
	// One edge, one cause. The description is the larger cause, so it names the
	// edge; the grain does not get to claim it as well.
	assert.equal(
		submitDerivationKind({ hasParent: true, canvasAspectChanged: false, textChanged: true, grainChanged: true }),
		'description_edit'
	);
});

test('T-10: a first draw has no parent and so no edge', () => {
	assert.equal(
		submitDerivationKind({ hasParent: false, canvasAspectChanged: false, textChanged: false, grainChanged: true }),
		null
	);
});

test('T-10: the new kind does not ride on an existing one', () => {
	const derivation = readFileSync(new URL('./derivation.ts', import.meta.url), 'utf8');
	assert.match(derivation, /sketch_grain_change: '写生の区切り'/);
	assert.match(derivation, /sketch_grain_change: 'Sketch grain'/);
});

// ------------------------------------------- every sender, not just the first

test('T-2/T-9: every request body that starts at Stage 2 carries the prose', () => {
	// Renaming or adding an API key means counting the senders: a receiver drops
	// what it does not know, so a missed sender stays a silent 200. Inside the
	// page there are several places that post to /api/compose directly rather
	// than through composeOne, and each one is a place the four consumers below
	// Stage 1 could quietly go back to reading the raw description.
	const page = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf8');
	const bodies = page.split(/apiFetch\(\s*['"]\/api\/compose['"]/).slice(1);
	assert.ok(bodies.length >= 4, `expected the known /api/compose senders, found ${bodies.length}`);
	for (const [i, body] of bodies.entries()) {
		const head = body.slice(0, 900);
		assert.match(head, /sketchPayloadFor\(/, `/api/compose sender ${i + 1} does not carry the prose`);
	}

	// And the paint path says whether the layer runs at all.
	const paint = page.slice(page.indexOf("apiFetch('/api/paint/stream'"));
	assert.match(paint.slice(0, 900), /sketch: resolvedSketchMode !== 'off'/);
});
