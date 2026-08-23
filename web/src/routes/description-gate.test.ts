// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-4 of contract tasks/description-is-the-origin.md.
//
// There is no component renderer here, so the derivations cannot be evaluated
// as Svelte runes.  Two halves are needed and neither alone is a gate: the
// behaviour of the rule (evaluated for real, on the same function the page
// imports) and the wiring (the page's own gate is written in terms of it).
// Assert only the wiring and any rule passes; assert only the behaviour and
// the page can go back to `input.trim()` while the test stays green.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { pipelineDescription } from '../lib/description-labels.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const page = fs.readFileSync(path.join(here, '+page.svelte'), 'utf8');
const batchOwner = fs.readFileSync(path.join(here, '../lib/features/batch/state.svelte.ts'), 'utf8');
const workOwner = fs.readFileSync(path.join(here, '../lib/features/work/state.svelte.ts'), 'utf8');

/** The single-mode gate, as the page writes it. */
const canSubmitSingle = (input: string) => !!pipelineDescription(input).trim();

/** The batch line filter, as the page writes it. */
const batchNonEmpty = (batchInput: string) =>
	batchInput.split('\n').filter((l) => pipelineDescription(l).trim()).length;

test('a description that is only labels cannot be sent', () => {
	for (const only of ['[note]', '1. ', '［疎  紀友則 / 古今和歌集（春下）］', '12) ', '３．']) {
		assert.equal(canSubmitSingle(only), false, only);
	}
});

test('a description that keeps a body can be sent', () => {
	for (const real of ['[note] 水面に光', '1. 水面に光', '水面に光', '［疎］ 花の散るらむ']) {
		assert.equal(canSubmitSingle(real), true, real);
	}
});

test('batch counts the lines that have something left to draw', () => {
	// The numbering is exactly what an author types in batch mode, so a line is
	// counted by its body and not by its label.
	assert.equal(batchNonEmpty('1. 水面に光\n2. 岸の下草\n3. '), 2);
	assert.equal(batchNonEmpty('[note]\n[demo]\n'), 0);
	assert.equal(batchNonEmpty('水面に光'), 1);
});

test('the page gates on the cut text, not on the raw text', () => {
	// The perturbation this catches: canSubmit going back to `!!input.trim()`.
	const gate = workOwner.slice(workOwner.indexOf('const canSubmit'));
	const body = gate.slice(0, gate.indexOf(');'));
	assert.match(body, /pipelineDescription\(input\)\.trim\(\)/);
	assert.doesNotMatch(body, /!!input\.trim\(\)/);

	assert.match(page, /paintable: \(text\) => !!pipelineDescription\(text\)\.trim\(\)/);
	assert.match(batchOwner, /numberedBatchLines\(this\.input, this\.deps\.paintable\)\.length/);

	// The rule is imported, never re-typed: the server owns it and the editor's
	// meter already reads the same copy.
	assert.match(workOwner, /import \{ pipelineDescription \} from '\$lib\/description-labels'/);
});

test('the batch run paints the same lines the counter counted', () => {
	// A counter and a runner that disagree would show "2 lines" and send 3, one
	// of which the server now refuses with a 400.
	assert.match(batchOwner, /const lines = numberedBatchLines\(this\.input, this\.deps\.paintable\)/);
	assert.match(page, /paintable: \(text\) => !!pipelineDescription\(text\)\.trim\(\)/);
});

test('the server tells the page which refusal this is', () => {
	// The sentinel is stable and the wording is authored in ja.ts, the way
	// "render capacity is full" already is.
	assert.match(page, /detail === 'description is only labels'/);
	assert.match(page, /t\(\)\.errorDescriptionOnlyLabels/);
});
