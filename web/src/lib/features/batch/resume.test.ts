import { test } from 'node:test';
import assert from 'node:assert/strict';

import {
	batchStoppedPartWay,
	conditionsOfWork,
	latestBatchWork,
	linesToResume,
	numberedBatchLines,
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
			stage1_model: 'nvidia:gemma-4',
			stage2_model: 'nvidia:gemma-4',
			render_color_catalog_id: 'sumi',
			sketch_grain: 'coarse',
			render_wild: true,
			render_canvas_aspect_id: 'tate',
		}),
		{
			stage1Model: 'nvidia:gemma-4',
			stage2Model: 'nvidia:gemma-4',
			catalogId: 'sumi',
			sketchGrain: 'coarse',
			wild: true,
			canvasAspectId: 'tate',
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
		sketchGrain: null,
		wild: null,
		canvasAspectId: null,
	});
	assert.equal(conditionsOfWork({ render_wild: false }).wild, false);
});
