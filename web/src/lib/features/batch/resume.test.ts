import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { sketchModeOf } from '../../sketch.ts';

import {
	batchStoppedPartWay,
	conditionsOfWork,
	latestBatchWork,
	linesToResume,
	numberedBatchLines,
	resumedWild,
	resumedComposition,
	type BatchWork,
} from './resume';

/**
 * T-60 … T-63: finishing a batch that stopped part-way.
 *
 * These drive the module, not the source text: what decides whether the button
 * appears and what it paints is arithmetic over a prompt and a listing, and can
 * be run for real. The wiring that carries the answer to the screen is read in
 * components/the-batch-picker-and-the-resume-button.test.ts.
 */

const PROMPT = '山の向こうに月が昇る\n夜の霧が広がる\n青いクレヨンの線が波打つ';
const paintable = (text: string) => text.trim() !== '';
const LINES = numberedBatchLines(PROMPT, paintable);

function work(line: number, description: string, extra: BatchWork = {}): BatchWork {
	return { batch_line_number: line, batch_run_id: 'run-1', source_text: description, ...extra };
}

test('T-60  a line keeps the number the prompt gave it, blank lines included', () => {
	assert.deepEqual(numberedBatchLines('あ\n\nい', paintable), [
		{ line: 1, input: 'あ' },
		{ line: 3, input: 'い' },
	]);
	// Not 1 and 2: the gutter numbers lines, and #3 has to name the third line
	// of the box rather than the second work.
});

test('T-60  a run that reached the last line has nothing to resume', () => {
	const finished = work(3, '青いクレヨンの線が波打つ');
	assert.equal(batchStoppedPartWay(LINES, finished), false);
});

test('T-60  a run that stopped short of the last line has', () => {
	const stopped = work(2, '夜の霧が広がる');
	assert.equal(batchStoppedPartWay(LINES, stopped), true);
});

test('T-60  with no work carrying a batch number, there is nothing to resume', () => {
	assert.equal(latestBatchWork([{ batch_line_number: null }, {}]), null);
	assert.equal(batchStoppedPartWay(LINES, null), false);
	// And an empty prompt cannot be part-way through anything.
	assert.equal(batchStoppedPartWay([], work(1, 'あ')), false);
});

test('T-60  the newest batch work is the one the answer is read off', () => {
	const works = [{ id: 'a' }, work(2, '夜の霧が広がる'), work(1, '山の向こうに月が昇る')];
	assert.equal(latestBatchWork(works), works[1]);
});

test('T-61  the number alone does not make it the same batch', () => {
	// Same position in the prompt, a description from some other run. Comparing
	// numbers only would offer to "finish" a batch this work never belonged to.
	const stranger = work(2, 'まったく別の記述');
	assert.equal(batchStoppedPartWay(LINES, stranger), false);
});

test('T-61  a number the prompt no longer has is not a resume point', () => {
	const beyond = work(9, '夜の霧が広がる');
	assert.equal(batchStoppedPartWay(LINES, beyond), false);
});

test('T-61  the description is read from the line, header and all', () => {
	// Works saved before source_text existed only carry the stored input, which
	// is the line with the run's own `#2 ` in front of it.
	const older: BatchWork = { batch_line_number: 2, batch_run_id: 'run-1', input: '#2 夜の霧が広がる' };
	assert.equal(batchStoppedPartWay(LINES, older), true);
});

test('T-62  resuming paints the lines that have no work', () => {
	const drawn = [work(2, '夜の霧が広がる'), work(1, '山の向こうに月が昇る')];
	assert.deepEqual(linesToResume(LINES, drawn, 'run-1'), [{ line: 3, input: '青いクレヨンの線が波打つ' }]);
});

test('T-62  a line that failed mid-run is painted, and the ones after it are not', () => {
	// Line 2 failed, 3 was painted, then the run was stopped. Resuming from "the
	// one after the last" would redraw 3; what is missing is 2.
	const drawn = [work(3, '青いクレヨンの線が波打つ'), work(1, '山の向こうに月が昇る')];
	assert.deepEqual(linesToResume(LINES, drawn, 'run-1'), [{ line: 2, input: '夜の霧が広がる' }]);
});

test('T-62  works from another run do not count as drawn', () => {
	const other = [{ batch_line_number: 2, batch_run_id: 'run-2', source_text: '夜の霧が広がる' }];
	assert.deepEqual(
		linesToResume(LINES, other, 'run-1').map((item) => item.line),
		[1, 2, 3],
	);
});

test('T-63  the conditions are read off the work that was drawn last', () => {
	assert.deepEqual(
		conditionsOfWork({
			draw_options: {route: 'read_and_draw', sketch: 'on', composition: 'on', wild: 'on',
				catalog: {id: 'sumi', mode: 'fixed'}, canvas_aspect: 'tate',
				models: {stage1: 'nvidia:gemma-4', stage2: 'nvidia:gemma-4'}},
		}),
		{
			stage1Model: 'nvidia:gemma-4',
			stage2Model: 'nvidia:gemma-4',
			catalogId: 'sumi',
			catalogMode: 'fixed',
			sketchGrain: 'on',
			wild: true,
			canvasAspectId: 'tate',
			route: 'read_and_draw',
			composition: 'on',
		},
	);
});

test('T-63  a condition the work never recorded is not invented', () => {
	// Every field null, and `wild` null rather than false: a work that predates
	// the switch did not have it turned off, and a caller told `false` would put
	// the author's switch down on their behalf.
	assert.deepEqual(conditionsOfWork({ batch_line_number: 1 }), {
		stage1Model: null,
		stage2Model: null,
		catalogId: null,
		catalogMode: null,
		sketchGrain: null,
		wild: null,
		canvasAspectId: null,
		route: null,
		composition: null,
	});
	assert.equal(conditionsOfWork({ render_wild: false }).wild, null);
});

test('resuming preserves current choices when switches were not recorded', () => {
	assert.equal(resumedWild(null, 'on'), 'on');
	assert.equal(resumedWild(null, 'off'), 'off');
	assert.equal(resumedWild(true, 'off'), 'on');
	assert.equal(resumedWild(false, 'on'), 'off');
	assert.equal(resumedComposition(null, 'on'), 'on');
	assert.equal(resumedComposition(null, 'off'), 'off');
	assert.equal(resumedComposition('on', 'off'), 'on');
	assert.equal(resumedComposition('off', 'on'), 'off');
});

test('batch resume restores recorded choices and leaves unrecorded choices as selected', async () => {
	const page = readFileSync(new URL('../../../routes/+page.svelte', import.meta.url), 'utf8');
	const source = page.slice(page.indexOf('async function applyBatchRunConditions('), page.indexOf('async function resumeInterruptedBatch('));
	const javascript = ts.transpile(source, { target: ts.ScriptTarget.ES2022 });
	const choices = { route: 'stages', sketch: 'on', composition: 'on', wild: 'on',
		catalog: { id: 'sumi', mode: 'auto' }, canvas_aspect: 'tate', models: { stage1: 'one', stage2: 'two' } };
	const apply = new Function('work', 'loadModelReferences', 'resumedComposition', 'resumedWild', 'sketchModeOf', 'normalizeCanvasAspectId',
		`${javascript}; return applyBatchRunConditions;`)({ batchTextOptions: choices }, async () => {}, resumedComposition, resumedWild, sketchModeOf, (id: string) => id);
	await apply({ stage1Model: null, stage2Model: null, catalogId: null, catalogMode: null,
		sketchGrain: null, wild: null, canvasAspectId: null, route: null, composition: null });
	assert.deepEqual(choices, { route: 'stages', sketch: 'off', composition: 'on', wild: 'on',
		catalog: { id: 'sumi', mode: 'auto' }, canvas_aspect: 'tate', models: { stage1: 'one', stage2: 'two' } });
	await apply({ stage1Model: 'new-one', stage2Model: 'new-two', catalogId: 'other', catalogMode: 'fixed',
		sketchGrain: 'on', wild: false, canvasAspectId: 'yoko', route: 'read_and_draw', composition: 'off' });
	assert.deepEqual(choices, { route: 'read_and_draw', sketch: 'on', composition: 'off', wild: 'off',
		catalog: { id: 'other', mode: 'fixed' }, canvas_aspect: 'yoko', models: { stage1: 'new-one', stage2: 'new-two' } });
});

test('T-66  a run made under auto says so, beside the catalog it resolved to', () => {
	// [I-257]. `auto` reads each description anew, so the resolved id is what the
	// last line happened to get. Both are kept: the mode says what was asked for,
	// the id is still what that line was drawn in.
	const auto = conditionsOfWork({ draw_options: {route: null, sketch: null, composition: null, wild: null,
		catalog: {mode: 'auto', id: 'sumi'}, canvas_aspect: null, models: null} });
	assert.equal(auto.catalogMode, 'auto');
	assert.equal(auto.catalogId, 'sumi');
});

test('T-66  a work older than the column is not called "not auto"', () => {
	// Null, not 'fixed'. Reading an absent column as a chosen catalog would tell
	// the resume to pin every batch drawn before the column to one catalog.
	assert.equal(conditionsOfWork({ render_color_catalog_id: 'sumi' }).catalogMode, null);
});
