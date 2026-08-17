// Run with: npm run test:unit  (node:test, no test dependency)
//
// 待っているあいだ、どの層が働いているかが画面に出る -- contract
// tasks/the-stream-says-which-layer-is-working.md ([I-302]), web side.
// T-248 (an event this build does not know is dropped) and T-252 (the
// indicator says four different things at the four moments, in both languages).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ja } from './i18n/ja.ts';
import { en } from './i18n/en.ts';
import type { LangPack } from './i18n/types.ts';
import { paintStageHandlers, paintStageLabel, readPaintStream } from './paintStream.ts';

const DONE = { event: 'done', ddl: '黒い円を中心に置く。', svg: '<svg/>' };

const streamOf = (events: object[]) =>
	new Response(events.map((e) => `${JSON.stringify(e)}\n`).join(''));

const describeError = (detail: unknown, status: number) => `HTTP ${status}: ${String(detail)}`;

// ---------------------------------------------------------------- T-248

test('T-248  an event this build has no word for is read and dropped', async () => {
	// The server may name a layer before the page learns the word for it. A
	// reader that threw on the unknown line would turn every such addition into
	// a broken draw, and the addition is the cheap half of the change.
	const seen: string[] = [];
	const done = await readPaintStream<typeof DONE>(
		streamOf([
			{ event: 'a-layer-that-does-not-exist-yet', elapsed_ms: 1 },
			{ event: 'sketch', sketch_state: 'fine' },
			{ event: 'stage1', tokens_in: 3, tokens_out: 4 },
			{ event: 'another-one-nobody-has-named' },
			{ event: 'score', instruction_count: 1 },
			DONE
		]),
		{
			describeError,
			onSketch: () => seen.push('sketch'),
			onStage1: () => seen.push('stage1'),
			onScore: () => seen.push('score')
		}
	);

	assert.deepEqual(seen, ['sketch', 'stage1', 'score']);
	assert.equal(done.ddl, DONE.ddl);
});

test('T-248  an error event is still an error, not another unknown line', async () => {
	// The reverse of the gate above: dropping what it does not know must not
	// become dropping what it does. Without this, deleting the error branch
	// would leave T-248 green and every failed draw silently "incomplete".
	await assert.rejects(
		readPaintStream(streamOf([{ event: 'error', status: 502, detail: 'interpret failed' }]), {
			describeError
		}),
		/HTTP 502: interpret failed/
	);
});

// ---------------------------------------------------------------- T-252

/** Drive the whole sequence and collect what the indicator said, in order. */
async function labelsThrough(strings: LangPack): Promise<string[]> {
	const labels: string[] = [];
	labels.push(paintStageLabel('requested', strings, { sketchOn: true }));
	await readPaintStream(
		streamOf([
			{ event: 'sketch', sketch_state: 'fine' },
			{ event: 'stage1', tokens_in: 3, tokens_out: 4 },
			{ event: 'score', instruction_count: 1 },
			DONE
		]),
		{
			describeError,
			...paintStageHandlers(strings, (label) => labels.push(label), { sketchOn: true })
		}
	);
	return labels;
}

test('T-252  the indicator says four different things at the four moments', async () => {
	// One test over both packs: the wording is ruled per language, but the
	// property -- four moments, four distinct non-empty labels -- is the same,
	// and a gate that only ran on ja would let en drift silently.
	for (const strings of [ja, en] as LangPack[]) {
		const labels = await labelsThrough(strings);

		assert.equal(labels.length, 4, `${strings.code}: one of the three switches is not wired`);
		for (const [i, label] of labels.entries()) {
			assert.ok(label.length > 0, `${strings.code}: label ${i} is empty`);
		}
		assert.equal(
			new Set(labels).size,
			4,
			`${strings.code}: two moments show the same words -- ${JSON.stringify(labels)}`
		);
	}
});

test('T-252  with the layer off the wait opens on interpretation, not on the sketch', async () => {
	// The only moment that is still guessed. The guess is now a small one, and
	// it has to follow what was actually asked for.
	for (const strings of [ja, en] as LangPack[]) {
		assert.equal(paintStageLabel('requested', strings, { sketchOn: false }), strings.stageInterpreting);
		assert.equal(paintStageLabel('requested', strings, { sketchOn: true }), strings.stageSketching);
	}
});
