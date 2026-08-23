// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for 写生 (Stage 0.5) in the generation info drawer. The drawer had
// no sketch row of any kind -- "sketch" did not occur once in CanvasPanel --
// so the one place that reports where a work came from said nothing about the
// layer that rewrote its description before Stage 1 ever read it.
//
// The describe panel does show a grain and the prose, but that is the working
// copy of the next draw and it is editable. The drawer reports the work on
// screen, which is a different work whenever the author is looking through the
// history. Reading the live control there would report the wrong work.
//
// T-36 (the drawer reports the work on screen, not the control), T-37 (every
// state the record can be in reaches a row, and an absent record is not
// rounded to off), T-38 (the section is Stage 0.5 and stands before Stage 1),
// T-39 (the prose is not repeated here -- the describe panel holds it),
// T-40 (the labels exist in both packs and in the type).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { SKETCH_STATES, sketchModeLabel, sketchStateNote, type SketchState } from './sketch.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const PANEL = read('./components/CanvasPanel.svelte');
const INFO = read('./features/canvas/CanvasGenerationInfo.svelte');

// ------------------------------------------------------------------- T-36

test('T-36  the drawer takes both sketch fields from the work on screen', () => {
	for (const field of ['sketch_state', 'sketch_grain']) {
		assert.match(
			INFO,
			new RegExp(`statusHistoryItem\\?\\.${field} \\?\\? result\\?\\.${field}`),
			`the drawer does not read ${field} from the displayed work`
		);
	}
});

test('T-36  and it does not read the control that draws the next work', () => {
	// Those live in +page.svelte and follow the author's editing, not the work.
	for (const live of ['sketchMode', 'sketchDraft', 'sketchEditing', 'sketchGrainOf']) {
		assert.doesNotMatch(INFO, new RegExp(`\\b${live}\\b`), `the drawer reads ${live}`);
	}
});

// ------------------------------------------------------------------- T-37

test('T-37  every state the record can be in reaches a row', () => {
	// The drawer shows a grain row when the state is a grain, and a sentence
	// otherwise. Between them nothing may fall through in silence -- four
	// separate events used to collapse into one blank.
	const states: (SketchState | null)[] = [...SKETCH_STATES, null];
	for (const state of states) {
		for (const isJapanese of [true, false]) {
			const grain = state === 'fine' || state === 'coarse' ? state : null;
			const shown = grain
				? sketchModeLabel(grain, isJapanese)
				: sketchStateNote(state, isJapanese);
			assert.ok(shown.trim().length > 0, `${state} says nothing (ja=${isJapanese})`);
		}
	}
});

test('T-37  an absent record is not rounded to a record that says off', () => {
	for (const isJapanese of [true, false]) {
		assert.notEqual(sketchStateNote(null, isJapanese), sketchStateNote('off', isJapanese));
	}
});

test('T-37  and the drawer renders exactly those two, each on its own condition', () => {
	assert.match(INFO, /\{#if detailSketchGrain\}/);
	assert.match(INFO, /\{#if detailSketchNote\}/);
	assert.match(INFO, /sketchStateNote\(detailSketchState, isJapanese\)/);
	// The grain of a work whose state is not a grain still comes from the record
	// (a failed run can carry the grain that was asked for).
	assert.match(INFO, /normalizeSketchGrain\(statusHistoryItem\?\.sketch_grain/);
});

// ------------------------------------------------------------------- T-38

test('T-38  the section is Stage 0.5, and it stands before Stage 1', () => {
	const sketch = INFO.indexOf('<h4>{t().sketchLabel}</h4>');
	const stage1 = INFO.indexOf('<h4>{t().provenanceSectionInterpretation}</h4>');
	assert.ok(sketch > 0, 'the drawer has no sketch section');
	assert.ok(stage1 > 0, 'the drawer has no interpretation section');
	assert.ok(sketch < stage1, 'the sketch section comes after interpretation');
	// The heading is the shared one, so the English never says "Sketch" alone.
	assert.match(read('./i18n/en.ts'), /sketchLabel: 'Sketch from life \(Stage 0\.5\)'/);
});

// ------------------------------------------------------------------- T-39

test('T-39  the prose is not repeated here; the describe panel holds it', () => {
	// Author decision, 2026-08-13. The drawer says what the layer did; the
	// paragraph it wrote belongs where there is room to read and edit it, and
	// showing it twice pushed interpretation and performance off the panel.
	assert.doesNotMatch(INFO, /detailSketchText/);
	assert.doesNotMatch(INFO, /sketch_text/);
	assert.doesNotMatch(INFO, /detail-sketch-text/);
	// It is still on screen, in the panel that owns it.
	assert.match(read('../routes/+page.svelte'), /class="sketch-body">\{work\.sketchDraft\}/);
});

test('T-39  and the section is withheld when there is no work at all', () => {
	assert.match(INFO, /\{#if hasSketchDetails\}/);
	assert.match(INFO, /hasSketchDetails = \$derived\(!!\(statusHistoryItem \?\? result\)\)/);
});

// ------------------------------------------------------------------- T-40

test('T-40  the new labels exist in both packs and in the type', () => {
	const ja = read('./i18n/ja.ts');
	const en = read('./i18n/en.ts');
	const types = read('./i18n/types.ts');
	for (const key of [
		'provenanceLabelSketchRecord',
		'provenanceHintSketchGrain',
		'provenanceHintSketchRecord'
	]) {
		assert.match(ja, new RegExp(`\\n\\t${key}: '`), `ja.ts has no ${key}`);
		assert.match(en, new RegExp(`\\n\\t${key}: '`), `en.ts has no ${key}`);
		assert.match(types, new RegExp(`\\n\\t${key}: string;`), `types.ts has no ${key}`);
		assert.match(INFO, new RegExp(`t\\(\\)\\.${key}`), `the drawer never uses ${key}`);
	}
	// The two keys the removed prose row used are gone from all three, so no
	// pack carries a label nothing shows.
	for (const key of ['provenanceLabelSketchText', 'provenanceHintSketchText']) {
		for (const [name, pack] of [['ja', ja], ['en', en], ['types', types]] as const) {
			assert.doesNotMatch(pack, new RegExp(key), `${name} still carries ${key}`);
		}
	}
});
