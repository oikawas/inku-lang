// Run with: npm run test:unit  (node:test, no test dependency)
//
// Sketch-from-life (Stage 0.5) acceptance, web side. T-9 verifies that the
// grain is a real option wired from both places that can start a draw; T-10
// verifies the genealogy edge.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { submitDerivationKind } from './derivation.ts';
import {
	DEFAULT_SKETCH_MODE,
	normalizeSketchGrain,
	normalizeSketchState,
	sketchGrainOf,
	sketchModeLabel,
	sketchModeNote,
	sketchModeOf,
	sketchStateNote,
	SKETCH_MODES,
	type SketchMode
} from './sketch.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

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
	const currentWork = read('./features/run/current-work.ts');
	assert.match(currentWork, /sketch:\s*sketchOn/);
	assert.match(currentWork, /sketch_grain: resolvedSketchGrain/);
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
	const notes = (['fallback', 'off', 'not_applicable'] as const).map((s) => sketchStateNote(s, true));
	notes.push(sketchStateNote(null, true));
	assert.equal(new Set(notes).size, 4, 'two of the four silences say the same thing');
	// A work whose prose is on screen needs no note: the prose is the answer.
	assert.equal(sketchStateNote('fine', true), '');
	assert.equal(sketchStateNote('coarse', false), '');
});

test('T-6: an absent or unknown state is not rounded to a real one', () => {
	assert.equal(normalizeSketchState(undefined), null);
	assert.equal(normalizeSketchState(null), null);
	assert.equal(normalizeSketchState(''), null);
	assert.equal(normalizeSketchState('sketched'), null);
	assert.equal(normalizeSketchState('off'), 'off');
	assert.equal(normalizeSketchState('not_applicable'), 'not_applicable');
});

test('T-6: both places that put a work on screen carry its state, and the panel shows it', () => {
	const page = read('../routes/+page.svelte');
	assert.match(page, /sketchState = normalizeSketchState\(state\)/);
	// A fresh run and a saved work reopened. Wiring one and not the other leaves
	// half the works reading as though they predate the column.
	assert.match(page, /adoptSketch\(r\.sketch_text \?\? null, r\.sketch_grain, input, r\.sketch_state\)/);
	assert.match(page, /adoptSketch\(it\.sketch_text \?\? null, it\.sketch_grain, sourceText, it\.sketch_state\)/);
	assert.match(page, /sketchStateNote\(sketchState, getLang\(\) === 'ja'\)/);
});

test('T-6/T-2: the one sender that saves a drawing carries the state too', () => {
	const page = read('../routes/+page.svelte');
	const bodies = page.split(/apiFetch\(\s*['"]\/api\/history['"]/).slice(1);
	assert.ok(bodies.length >= 1, 'the /api/history sender is missing');
	for (const [i, body] of bodies.entries()) {
		assert.match(body.slice(0, 4000), /sketch_state/, `/api/history sender ${i + 1} drops the state`);
	}
	// And the two works saved from a compose response take the state from it
	// rather than leaving the server to guess.
	assert.equal((page.match(/sketch_state: composed\.sketch_state \?\? null/g) ?? []).length, 2);
});

// ------------------------------------------------------------------- T-10

test('T-10: the menu marks off as not recommended, in both languages', () => {
	assert.equal(sketchModeNote('off', true), '（推奨しない）');
	assert.equal(sketchModeNote('off', false), '(not recommended)');
	assert.equal(sketchModeNote('fine', true), '');
	assert.equal(sketchModeNote('coarse', false), '');

	const select = read('./components/SketchSelect.svelte');
	const menu = select.slice(select.indexOf('{:else}'), select.indexOf('<style>'));
	assert.match(menu, /sketchModeNote\(mode, isJapanese\)/);
});

test('T-10: and the three places that are not the menu do not say it', () => {
	// Those three render sketchModeLabel. Folding the note into the label is the
	// implementation that passes "it appears" while the note follows the label
	// everywhere -- including the lineage panel, where it would attach itself to
	// a work already drawn and read as a judgement of it.
	const labels: [SketchMode, string, string][] = [
		['off', '切', 'Off'],
		['fine', '細かく', 'Fine'],
		['coarse', '大きく', 'Coarse']
	];
	for (const [mode, ja, en] of labels) {
		assert.equal(sketchModeLabel(mode, true), ja);
		assert.equal(sketchModeLabel(mode, false), en);
	}

	// The compact toggle inside the same component is the fourth caller, and it
	// is above the {:else} that starts the menu.
	const select = read('./components/SketchSelect.svelte');
	const compact = select.slice(select.indexOf('{#if compact}'), select.indexOf('{:else}'));
	assert.ok(compact.length > 0);
	assert.doesNotMatch(compact, /sketchModeNote/);

	assert.doesNotMatch(read('./components/InputPanel.svelte'), /sketchModeNote/);
	assert.doesNotMatch(read('./components/LineagePanel.svelte'), /sketchModeNote/);
	// A fifth caller the contract's table did not list: the run summary in the
	// describe panel, which reports the grain of the work on screen.
	assert.doesNotMatch(read('../routes/+page.svelte'), /sketchModeNote/);
});

test('T-10: the note is its own element, not text joined onto the label', () => {
	// Joined, it would be indistinguishable from the label's return value, and
	// the gate above could no longer tell the two apart either.
	const select = read('./components/SketchSelect.svelte');
	assert.match(select, /<span class="option-label">\{sketchModeLabel\(mode, isJapanese\)\}<\/span/);
	assert.match(select, /<span class="option-note"\s*>\{sketchModeNote\(mode, isJapanese\)\}<\/span/);
});
