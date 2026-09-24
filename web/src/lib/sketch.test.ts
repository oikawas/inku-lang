// Run with: npm run test:unit  (node:test, no test dependency)
//
// Sketch-from-life acceptance, web side. The sketch supplements place and
// light beside the description, off by default and on when the author asks. T-9 verifies the choice is wired from every place that starts a draw;
// T-10 verifies the genealogy edge.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { submitDerivationKind } from './derivation.ts';
import {
	DEFAULT_SKETCH_MODE,
	normalizeSketchGrain,
	normalizeSketchState,
	sketchGrainLabel,
	sketchModeLabel,
	sketchModeNote,
	sketchModeOf,
	sketchStateNote,
	SKETCH_MODES,
	type SketchMode
} from './sketch.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

// ---------------------------------------------------------------- T-9 (mode)

test('T-9: a draw with no choice made has no sketch', () => {
	assert.equal(DEFAULT_SKETCH_MODE, 'off');
});

test('T-9: the control offers off and on', () => {
	assert.deepEqual(SKETCH_MODES, ['off', 'on']);
});

test('T-9: a saved choice reads back; a grain saved before the supplement sketch reads as on', () => {
	assert.equal(normalizeSketchGrain(undefined), null);
	assert.equal(normalizeSketchGrain('segmented'), null);
	assert.equal(sketchModeOf(undefined), 'off');
	assert.equal(sketchModeOf('on'), 'on');
	assert.equal(sketchModeOf('coarse'), 'on');
	assert.equal(sketchModeOf('fine'), 'on');
});

test('T-9: the work menu redraws with the sketch off or on', () => {
	const panel = read('./components/LineagePanel.svelte');
	assert.match(panel, /onDrawSketchGrain: \(node: LineageNode, mode: SketchMode/);
	const dialog = read('./components/WorkEditDialog.svelte');
	assert.match(dialog, /modes=\{\['off', 'on'\]\}/);

	const page = read('../routes/+page.svelte');
	// The menu path asks for a specific mode and must NOT hand over the stored
	// sketch: the choice is what changed, so the sketch is asked again or dropped.
	const handler = page.slice(
		page.indexOf('async function drawLineageSketchGrain'),
		page.indexOf('async function drawLineageDdlEdit')
	);
	assert.ok(handler.length > 0, 'the work-menu handler is missing');
	assert.match(handler, /sketchMode: mode/);
	assert.match(handler, /derivationKind: 'sketch_grain_change'/);
	assert.doesNotMatch(handler, /sketchText/);
});

test('T-9: both draw paths send the chosen mode', () => {
	const work = read('./features/work/state.svelte.ts');
	const currentWork = read('./features/run/current-work.ts');
	assert.match(currentWork, /sketch:\s*sketchOn/);
	assert.match(work, /sketch: options\.sketchMode \?\? sketchMode/);
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

test('T-10: the edge is named for the sketch, not the retired grain', () => {
	const derivation = read('./derivation.ts');
	assert.match(derivation, /sketch_grain_change: '写生の有無'/);
	assert.match(derivation, /sketch_grain_change: 'Sketch from life'/);
});
// ------------------------------------------- every sender, not just the first

test('T-2/T-9: every request body that starts at Stage 2 carries the prose', () => {
	// Renaming or adding an API key means counting the senders: a receiver drops
	// what it does not know, so a missed sender stays a silent 200. Inside the
	// the route and Work owner there are several places that post to /api/compose
	// directly rather than through composeOne, and each one is a place the four consumers below
	// Stage 1 could quietly go back to reading the raw description.
	const page = readFileSync(new URL('../routes/+page.svelte', import.meta.url), 'utf8');
	const work = read('./features/work/state.svelte.ts');
	const refinement = read('./features/canvas/refinement-coordinator.svelte.ts');
	const bodies = [page, work, refinement].flatMap((source) => source.split(/apiFetch\(\s*['"]\/api\/compose['"]/).slice(1));
	assert.ok(bodies.length >= 3, `expected the known /api/compose senders, found ${bodies.length}`);
	for (const [i, body] of bodies.entries()) {
		const head = body.slice(0, 900);
		assert.match(head, /sketchPayloadFor\(/, `/api/compose sender ${i + 1} does not carry the prose`);
	}

	// And the paint path says whether the layer runs at all.
	const currentWork = read('./features/run/current-work.ts');
	const paint = currentWork.slice(currentWork.indexOf("capabilities.apiFetch('/api/paint/stream'"));
	assert.match(paint.slice(0, 900), /sketch: sketchOn/);
});

// ═══════════════════ Sketch-from-life state (sketch_state)
//
// T-6 (a work with no record is not a work drawn with the layer off) and
// T-10 (the menu says "not recommended", and only the menu).

// -------------------------------------------------------------------- T-6

test('T-6: a work with no record does not read as a work drawn with the layer off', () => {
	// The whole point of the column. If these two ever return the same string,
	// four separate events have collapsed back into one silence.
	assert.notEqual(sketchStateNote(null, true), sketchStateNote('off', true));
	assert.notEqual(sketchStateNote(null, false), sketchStateNote('off', false));
	assert.ok(sketchStateNote(null, true).length > 0);
	assert.ok(sketchStateNote(null, false).length > 0);
	assert.ok(sketchStateNote('off', true).length > 0);
});

test('T-6: a failed layer and a route that never runs it read apart from both', () => {
	const notes = (['fallback', 'off', 'not_applicable', 'not_needed'] as const).map((s) => sketchStateNote(s, true));
	notes.push(sketchStateNote(null, true));
	assert.equal(new Set(notes).size, 5, 'two of the five silences say the same thing');
	// A work whose sketch is on screen needs no note: the sketch is the answer.
	assert.equal(sketchStateNote('fine', true), '');
	assert.equal(sketchStateNote('coarse', false), '');
	assert.ok(sketchStateNote('supplemented', true).length > 0);
});

test('T-6: an absent or unknown state is not rounded to a real one', () => {
	assert.equal(normalizeSketchState(undefined), null);
	assert.equal(normalizeSketchState(null), null);
	assert.equal(normalizeSketchState(''), null);
	assert.equal(normalizeSketchState('sketched'), null);
	assert.equal(normalizeSketchState('off'), 'off');
	assert.equal(normalizeSketchState('not_applicable'), 'not_applicable');
	assert.equal(normalizeSketchState('not_needed'), 'not_needed');
	assert.equal(normalizeSketchState('supplemented'), 'supplemented');
});

test('T-6: both places that put a work on screen carry its state, and the panel shows it', () => {
	const page = read('../routes/+page.svelte');
	const work = read('./features/work/state.svelte.ts');
	const currentWork = read('./features/history/current-work.ts');
	const generationInfo = read('./features/canvas/CanvasGenerationInfo.svelte');
	assert.match(work, /sketchState = normalizeSketchState\(state\)/);
	// A fresh run and a saved work reopened. Wiring one and not the other leaves
	// half the works reading as though they predate the column. Saved-work field
	// mapping now belongs to the canonical current-work projection.
	assert.match(work, /adoptSketch\(painted\.sketch_text \?\? null, painted\.sketch_grain, view\.description, painted\.sketch_state\)/);
	assert.match(currentWork, /sketchState: item\.sketch_state/);
	assert.match(page, /work\.adoptSketch\(projection\.sketchText, projection\.sketchGrain, projection\.sourceText, projection\.sketchState\)/);
	assert.match(page, /sketchStateNote\(work\.sketchState, getLang\(\) === 'ja'\)/);
	assert.match(generationInfo, /normalizeSketchState\(statusHistoryItem\?\.sketch_state \?\? result\?\.sketch_state\)/);
});

test('T-6/T-2: every sender that saves a drawing carries the state too', () => {
	const page = read('../routes/+page.svelte');
	const demo = read('./features/demo/state.svelte.ts');
	const historySave = read('./features/history/save.ts');
	const bodies = [demo, historySave].flatMap((source) => source.split(/apiFetch\(\s*['"]\/api\/history['"]/).slice(1));
	assert.equal(bodies.length, 2, 'a canonical /api/history sender is missing');
	for (const [i, body] of bodies.entries()) {
		assert.match(body.slice(0, 4000), /sketch_state/, `/api/history sender ${i + 1} drops the state`);
	}
});

// ------------------------------------------------------------------- T-10

test('T-10: no choice is discouraged any more', () => {
	for (const mode of SKETCH_MODES) {
		assert.equal(sketchModeNote(mode, true), '');
		assert.equal(sketchModeNote(mode, false), '');
	}
	const select = read('./components/SketchSelect.svelte');
	const menu = select.slice(select.indexOf('{:else}'), select.indexOf('<style>'));
	assert.match(menu, /sketchModeNote\(mode, isJapanese\)/);
});

test('T-10: the labels name the choice, and a retired grain keeps its own label', () => {
	const labels: [SketchMode, string, string][] = [
		['off', 'なし', 'Off'],
		['on', 'あり', 'On']
	];
	for (const [mode, ja, en] of labels) {
		assert.equal(sketchModeLabel(mode, true), ja);
		assert.equal(sketchModeLabel(mode, false), en);
	}
	assert.equal(sketchGrainLabel('fine', true), '細かく');
	assert.equal(sketchGrainLabel('coarse', false), 'Coarse');

	const select = read('./components/SketchSelect.svelte');
	const compact = select.slice(select.indexOf('{#if compact}'), select.indexOf('{:else}'));
	assert.ok(compact.length > 0);
	assert.doesNotMatch(compact, /sketchModeNote/);
	assert.doesNotMatch(read('./components/InputPanel.svelte'), /sketchModeNote/);
	assert.doesNotMatch(read('./components/LineagePanel.svelte'), /sketchModeNote/);
	assert.doesNotMatch(read('../routes/+page.svelte'), /sketchModeNote/);
});

test('T-10: the note is its own element, not text joined onto the label', () => {
	const select = read('./components/SketchSelect.svelte');
	assert.match(select, /<span class="option-label">\{sketchModeLabel\(mode, isJapanese\)\}<\/span/);
	assert.match(select, /<span class="option-note"\s*>\{sketchModeNote\(mode, isJapanese\)\}<\/span/);
});
