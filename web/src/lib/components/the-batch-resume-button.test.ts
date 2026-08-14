import { test } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

/**
 * T-64 and T-65: the button that finishes a batch which stopped part-way.
 *
 * The rules it runs on are driven for real in features/batch/resume.test.ts.
 * What is read here is the wiring that carries the answer to the screen, which
 * has no harness to run in: `test:unit` is `node --test` with no DOM.
 */

const PANEL = readFileSync(fileURLToPath(new URL('./BatchPanel.svelte', import.meta.url)), 'utf8');
const PAGE = readFileSync(fileURLToPath(new URL('../../routes/+page.svelte', import.meta.url)), 'utf8');

test('T-64  the resume button is withheld unless there is something to finish', () => {
	assert.match(PANEL, /\{#if canResumeBatch\}/, 'the resume button no longer depends on the flag');
	// Null the rest of the time -- an empty history and a run that reached its
	// last line are the same answer here, and both withhold the button.
	assert.match(PAGE, /canResumeBatch=\{batchResume !== null\}/, 'the flag is not the resume state');
	assert.match(PAGE, /if \(!currentUser \|\| !prompt\) \{ batchResume = null; return; \}/,
		'a member with no stored batch is offered a resume');
});

test('T-64  it sits to the left of the paint button', () => {
	const row = PANEL.match(/<div class="batch-actions">[\s\S]*?<\/div>/);
	assert.ok(row, 'the two buttons are no longer in one row');
	assert.ok(
		row[0].indexOf('batch-resume-btn') < row[0].indexOf('<PaintButton'),
		'the resume button is not before the paint button',
	);
});

test('T-65  a resumed run paints the plan, not the box', () => {
	assert.match(PAGE, /const paintLines = options\.resumeLines \?\? lines;/, 'the resume plan is not what gets painted');
	// Every quantity the run reads has to come from the plan, or the progress
	// readout counts one thing while the loop paints another.
	assert.match(PAGE, /const batchLineTotal = paintLines\.length;/);
	assert.match(PAGE, /for \(let i = 0; i < paintLines\.length; i\+\+\)/);
	assert.match(PAGE, /await paintBatchLine\(paintLines\[i\]\)/);
});

test('T-65  the numbers on the works come from the prompt, not from the plan', () => {
	// `item.line` throughout, never the loop index: resuming at line 7 has to put
	// #7 on the work, and a plan of what is left would otherwise restart at #1.
	assert.match(PAGE, /historyInput: `#\$\{item\.line\} \$\{item\.input\}`/);
	assert.match(PAGE, /displayLabel: `#\$\{item\.line\}`/);
	assert.match(PAGE, /batchLineNumber: item\.line/);
	// And the box is refilled with the whole batch, which is what those numbers
	// number.
	assert.match(PAGE, /batchInput = resume\.prompt;/);
});

test('T-65  the answer is asked for again when a run ends', () => {
	// A run that was stopped leaves lines to finish and a run that reached the
	// end leaves none; without this the button outlives the run it belonged to.
	assert.match(PAGE, /await refreshBatchResume\(\);/, 'the resume state is not refreshed after a run');
	assert.match(PAGE, /if \(mode === 'batch'\) void untrack\(refreshBatchResume\)/, 'the batch tab does not ask on arrival');
});
