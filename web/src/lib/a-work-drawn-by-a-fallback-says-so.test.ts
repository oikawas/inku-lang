// Run with: npm run test:unit  (node:test, no test dependency)
//
// 作曲フォールバックの記録 acceptance, web side --
// contract a-work-drawn-by-a-fallback-says-so.md.
//
// T-232 (the web sender), T-235 (the mark reads both layers), T-236 (the
// wording names its layer), T-237/T-238/T-239 (asking once before refining
// from a marked work), T-241 (three states in the drawer).
//
// The derivations are tested directly and the wiring is read out of the
// sources that use them. Either alone is a vacuous gate: a pure function
// nothing calls proves nothing, and a source that mentions a name proves
// nothing about what the name returns.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
	COMPOSE_FALLBACK_NONE,
	composeFallbackReason,
	composeFallbackState,
	composeFallbackValue,
	hasFallbackMark
} from './composeFallback.ts';
import {
	needsFallbackRefineConfirm,
	rememberFallbackRefineConfirm
} from './fallbackRefineGate.ts';
import { ja } from './i18n/ja.ts';
import { en } from './i18n/en.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const PAGE = read('../routes/+page.svelte');
const CANVAS = read('./components/CanvasPanel.svelte');
const THUMBNAIL = read('./components/HistoryThumbnail.svelte');

// ---------------------------------------------------------------------- T-232

test('T-232 the web sender stacks the reason when compose fell', () => {
	assert.equal(
		composeFallbackValue({ compose_fallback_used: true, compose_retry_reasons: ['stage2_hard_timeout'] }),
		'stage2_hard_timeout'
	);
	// Fell with nothing to say why: still a statement that it fell.
	assert.equal(composeFallbackValue({ compose_fallback_used: true }), 'stage2_fallback');
	assert.equal(
		composeFallbackValue({ compose_fallback_used: true, compose_retry_reasons: ['  '] }),
		'stage2_fallback'
	);
});

test('T-232 the web sender stacks none when compose held', () => {
	assert.equal(composeFallbackValue({ compose_fallback_used: false }), COMPOSE_FALLBACK_NONE);
	assert.equal(composeFallbackValue({}), COMPOSE_FALLBACK_NONE);
	assert.equal(COMPOSE_FALLBACK_NONE, 'none');
});

test('T-232 both saves to /api/history carry the value', () => {
	// Counted, not assumed: this page posts to the endpoint from two places --
	// the general save and the demo save -- and a key added to one of them is
	// the failure this counts. The bodies are single expressions, so each POST
	// is read as the text between its url and its closing brace.
	const posts = [...PAGE.matchAll(/apiFetch\('\/api\/history',[\s\S]{0,6000}?\n\t*\}\);/g)].map((m) => m[0]);
	assert.equal(posts.length, 2, `expected 2 saves to /api/history, saw ${posts.length}`);
	for (const [index, body] of posts.entries()) {
		assert.ok(
			body.includes('compose_fallback'),
			`the save at index ${index} does not say what compose did`
		);
	}
	// And the value sent is the derived one, never the raw flag.
	assert.ok(PAGE.includes('composeFallbackValue('), 'the page does not derive the value it sends');
});

// ---------------------------------------------------------------------- T-235

test('T-235 the mark is derived from either layer', () => {
	assert.equal(hasFallbackMark({ interpret_fallback: 'stage1_hard_timeout' }), true);
	assert.equal(hasFallbackMark({ compose_fallback: 'stage2_hard_timeout' }), true);
	assert.equal(
		hasFallbackMark({ interpret_fallback: 'stage1_empty_output', compose_fallback: 'stage2_fallback' }),
		true
	);
	assert.equal(hasFallbackMark({ interpret_fallback: null, compose_fallback: COMPOSE_FALLBACK_NONE }), false);
});

test('T-235 a work with no record carries no mark', () => {
	// The whole point of the column: nothing recorded is not the same as
	// nothing wrong, but it is not a mark either -- the 3,459 works drawn
	// before it would otherwise all wear one.
	assert.equal(hasFallbackMark({}), false);
	assert.equal(hasFallbackMark({ interpret_fallback: null, compose_fallback: null }), false);
	assert.equal(composeFallbackReason(null), null);
	assert.equal(composeFallbackReason(undefined), null);
	assert.equal(composeFallbackReason(COMPOSE_FALLBACK_NONE), null);
	assert.equal(composeFallbackReason('stage2_fallback'), 'stage2_fallback');
});

test('T-235 both places that draw the mark ask the shared derivation', () => {
	// Two components draw it. If either kept its own condition, a listing and a
	// canvas could disagree about the same work and only one would be corrected
	// when the rule moves.
	assert.ok(THUMBNAIL.includes('hasFallbackMark(item)'), 'the listing mark has its own condition');
	assert.ok(
		THUMBNAIL.includes("from '$lib/composeFallback'"),
		'the listing does not import the shared derivation'
	);
	assert.ok(
		CANVAS.includes('composeFallbackReason(') && CANVAS.includes("from '$lib/composeFallback'"),
		'the canvas badge does not use the shared derivation'
	);
	// And the badge is shown for Stage 2, not only for Stage 1.
	assert.ok(
		CANVAS.includes('composeFallbackDrawnReason'),
		'the canvas never shows a badge for the compose layer'
	);
});

// ---------------------------------------------------------------------- T-236

test('T-236 the badge wording exists in both languages and names its layer', () => {
	for (const pack of [ja, en]) {
		assert.equal(typeof pack.composeFallbackBadge, 'string');
		assert.ok(pack.composeFallbackBadge.trim().length > 0);
		assert.equal(typeof pack.composeFallbackHint, 'function');
		// The two layers are told apart by the words, not by position: a reader
		// seeing one badge has to know which stage lost the description.
		assert.notEqual(pack.composeFallbackBadge, pack.interpretFallbackBadge);
	}
	assert.equal(ja.composeFallbackBadge, '作曲フォールバック');
	assert.equal(ja.interpretFallbackBadge, '解釈フォールバック');
	// GLOSSARY: `composition` is the word for placement, so the English badge
	// says Score -- `Composition fallback` would collide with composition_seed.
	assert.equal(en.composeFallbackBadge, 'Score fallback');
	assert.ok(!en.composeFallbackBadge.toLowerCase().includes('composition'));
	// The hint names the stage and differs by reason.
	assert.notEqual(
		en.composeFallbackHint('stage2_hard_timeout'),
		en.composeFallbackHint('stage2_empty_output')
	);
	assert.notEqual(
		ja.composeFallbackHint('stage2_hard_timeout'),
		ja.composeFallbackHint('stage2_empty_output')
	);
});

// -------------------------------------------------------------- T-237 / T-238

test('T-237 refining from a marked work asks before it runs', () => {
	const asked = new Set<string>();
	assert.equal(
		needsFallbackRefineConfirm({ id: 'w1', compose_fallback: 'stage2_fallback' }, asked),
		true
	);
	assert.equal(
		needsFallbackRefineConfirm({ id: 'w2', interpret_fallback: 'stage1_hard_timeout' }, asked),
		true
	);
});

test('T-237 every refinement passes through the gate before it draws', () => {
	// Counted from the source, because the refinements do not leave from one
	// place: eight actions start one, and a gate on seven of them is a gate on
	// none of the works that go through the eighth.
	const REFINEMENTS = [
		'async function submit(',
		'async function replay(',
		'async function varyPerformance(',
		'async function varyComposition(',
		'async function varyInterpretation(',
		'async function generateVariationCandidates(',
		'async function drawLineageDescriptionEdit(',
		'async function drawLineageSketchGrain(',
		'async function drawLineageDdlEdit('
	];
	const ungated: string[] = [];
	for (const opening of REFINEMENTS) {
		const start = PAGE.indexOf(opening);
		assert.notEqual(start, -1, `the page no longer has ${opening} -- recount the entry points`);
		// The gate belongs at the head of the action, before anything is drawn
		// or saved. Only the opening stretch is read, so a call further down
		// (after the work is already written) does not count as gated.
		const head = PAGE.slice(start, start + 1400);
		if (!head.includes('confirmFallbackRefine(')) ungated.push(opening);
	}
	assert.deepEqual(ungated, [], `these refinements draw without asking: ${ungated.join(', ')}`);
	assert.equal(REFINEMENTS.length, 9, 'the census no longer counts nine refinements');
	// The gate itself has to be able to say no. A dialog whose cancel resolves
	// nothing leaves the caller waiting for ever, and one that resolves true
	// would run the refinement the author refused.
	assert.ok(PAGE.includes('cancelRun: () => resolve(false)'), 'cancelling never reaches the caller');
	assert.ok(PAGE.includes('cancel?.()'), 'the dialog does not run its cancel callback');
});

test('T-238 the same work is not asked about twice', () => {
	const asked = new Set<string>();
	const work = { id: 'w1', compose_fallback: 'stage2_hard_timeout' };

	assert.equal(needsFallbackRefineConfirm(work, asked), true);
	rememberFallbackRefineConfirm(work, asked);
	assert.equal(needsFallbackRefineConfirm(work, asked), false);
	// Another marked work is its own decision.
	assert.equal(needsFallbackRefineConfirm({ id: 'w2', compose_fallback: 'x' }, asked), true);
	// And remembering is only done after the author answered: the page calls it
	// from `run`, never beside the dialog.
	assert.ok(
		/run: \(\) => \{ rememberFallbackRefineConfirm\(/.test(PAGE),
		'the page remembers the answer somewhere other than in the answer'
	);
});

// ---------------------------------------------------------------------- T-239

test('T-239 an unmarked work is not asked about', () => {
	const asked = new Set<string>();
	assert.equal(needsFallbackRefineConfirm({ id: 'w1' }, asked), false);
	assert.equal(needsFallbackRefineConfirm({ id: 'w1', compose_fallback: COMPOSE_FALLBACK_NONE }, asked), false);
	assert.equal(needsFallbackRefineConfirm(null, asked), false);
	assert.equal(needsFallbackRefineConfirm(undefined, asked), false);
	// Nothing was remembered either -- an unmarked work never reached the dialog.
	assert.equal(asked.size, 0);
});

// ---------------------------------------------------------------------- T-241

test('T-241 the drawer tells the three states apart', () => {
	assert.equal(composeFallbackState('stage2_hard_timeout'), 'yes');
	assert.equal(composeFallbackState(COMPOSE_FALLBACK_NONE), 'no');
	assert.equal(composeFallbackState(null), 'unrecorded');
	assert.equal(composeFallbackState(undefined), 'unrecorded');
	assert.equal(composeFallbackState(''), 'unrecorded');

	// Three readings, three words, in both languages.
	for (const pack of [ja, en]) {
		const words = new Set([
			pack.composeFallbackRecord('yes'),
			pack.composeFallbackRecord('no'),
			pack.composeFallbackRecord('unrecorded')
		]);
		assert.equal(words.size, 3, 'two of the three states read the same');
	}
	assert.equal(ja.composeFallbackRecord('unrecorded'), '記録なし');
	assert.equal(en.composeFallbackRecord('unrecorded'), 'Not recorded');
});

test('T-241 the sender writes none so the drawer can tell', () => {
	// Without this, a work whose compose held is stored as NULL and the drawer
	// reads it as unrecorded -- the same as a work from before the column. The
	// perturbation that drops it is invisible to every other gate here.
	assert.equal(composeFallbackState(composeFallbackValue({ compose_fallback_used: false })), 'no');
	assert.equal(
		composeFallbackState(composeFallbackValue({ compose_fallback_used: true })),
		'yes'
	);
});

test('T-241 the drawer shows the record for every work, not only for a fallback', () => {
	// Shown unconditionally: a row that appears only when the stage fell can
	// never say "not recorded", which is the reading the column was added for.
	assert.ok(
		CANVAS.includes('composeFallbackRecord'),
		'the canvas drawer does not show the three-state record'
	);
	assert.ok(
		PAGE.includes('composeFallbackRecord'),
		'the result log does not show the three-state record'
	);
	// The mark, unlike the drawer, is only for the works that fell.
	assert.ok(
		!THUMBNAIL.includes('composeFallbackState'),
		'the listing mark reads the three-state record instead of the mark condition'
	);
});
