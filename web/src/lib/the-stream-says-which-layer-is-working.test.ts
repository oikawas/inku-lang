// Run with: npm run test:unit  (node:test, no test dependency)
//
// The screen identifies the active layer while the reader waits -- contract
// tasks/the-stream-says-which-layer-is-working.md ([I-302]), web side.
// T-248 (an event this build does not know is dropped) and T-252 (the
// indicator says four different things at the four moments, in both languages).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ja } from './i18n/ja.ts';
import { en } from './i18n/en.ts';
import type { LangPack } from './i18n/types.ts';
import { paintStageHandlers, paintStageLabel, providerAttemptText, readPaintStream, runningStageLabel } from './paintStream.ts';

const DONE = { event: 'done', ddl: '黒い円を中心に置く。', svg: '<svg/>' };

const streamOf = (events: object[]) =>
	new Response(events.map((e) => `${JSON.stringify(e)}\n`).join(''));

const streamFromBytes = (chunks: Uint8Array[]) =>
	new Response(new ReadableStream({
		start(controller) {
			for (const chunk of chunks) controller.enqueue(chunk);
			controller.close();
		}
	}));

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

test('a terminal event without a final newline is still consumed', async () => {
	const done = await readPaintStream<typeof DONE>(new Response(JSON.stringify(DONE)), { describeError });
	assert.deepEqual(done, DONE);
});

test('a multibyte event split between chunks is flushed without corruption', async () => {
	const bytes = new TextEncoder().encode(JSON.stringify(DONE));
	const multibyteStart = bytes.indexOf(0xe9);
	assert.ok(multibyteStart >= 0, 'fixture must contain a three-byte UTF-8 character');
	const done = await readPaintStream<typeof DONE>(
		streamFromBytes([bytes.slice(0, multibyteStart + 1), bytes.slice(multibyteStart + 1)]),
		{ describeError }
	);
	assert.deepEqual(done, DONE);
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

// ---------------------------------------------------------------- W4

test('a retry reads as a retry, not as a longer wait', async () => {
	// The Server review's W4: the indicator showed only elapsed time, so a
	// first attempt that timed out looked like a slow answer.
	const shown: string[] = [];
	await readPaintStream(
		streamOf([
			{ event: 'attempt', provider_attempt: { action: 'generate_normalized_ddl', attempt: 1, max_attempts: 4 } },
			{ event: 'attempt', provider_attempt: { action: 'generate_normalized_ddl', attempt: 2, max_attempts: 4 } },
			{ event: 'stage1', tokens_in: 3, tokens_out: 4 },
			{ event: 'attempt', provider_attempt: null },
			DONE
		]),
		{ describeError, onAttempt: (event) => shown.push(providerAttemptText(event.provider_attempt, ja)) }
	);
	assert.deepEqual(shown, ['応答待ち（1/4回目）', '再試行中（2/4回目）', '']);
	assert.equal(providerAttemptText({ attempt: 2, max_attempts: 4 }, en), 'Retrying (try 2/4)');
});

test('completion asked again is shown separately from a communication retry', async () => {
	for (const strings of [ja, en]) {
		const shown: string[] = [];
		await readPaintStream(streamOf([
			{ event: 'attempt', provider_attempt: { action: 'complete_visible_ddl_holes', attempt: 2, max_attempts: 4, asked_again: true } },
			{ event: 'attempt', provider_attempt: { action: 'complete_visible_ddl_holes', attempt: 3, max_attempts: 4 } },
			DONE,
		]), { describeError, onAttempt: (event) => shown.push(providerAttemptText(event.provider_attempt, strings)) });
		assert.deepEqual(shown, strings.code === 'ja'
			? ['断られた案を理由を添えて問い直し中（2/4回目）', '再試行中（3/4回目）']
			: ['Asking again with the reasons the proposal was refused (2/4)', 'Retrying (try 3/4)']);
	}
});

// ---------------------------------------------------------------- composition reading

test('the composition reading names itself while it runs', () => {
	// The core and the Server already report the running call's action; the
	// reading used to wait under the label of the layer before it (2026-10-13).
	for (const strings of [ja, en] as LangPack[]) {
		const reading = { action: 'read_composition', attempt: 1, max_attempts: 2 };
		assert.equal(runningStageLabel(strings.stageInterpreting, reading, strings), strings.stageReadingComposition);
		assert.equal(runningStageLabel(strings.stageDdlGenerating, reading, strings), strings.stageReadingComposition);
		const drafting = { action: 'generate_normalized_ddl', attempt: 1, max_attempts: 4 };
		assert.equal(runningStageLabel(strings.stageDdlGenerating, drafting, strings), strings.stageDdlGenerating);
		assert.equal(runningStageLabel(strings.stageInterpreting, null, strings), strings.stageInterpreting);
		const others = [
			strings.stageSketching,
			strings.stageInterpreting,
			strings.stageStructuring(''),
			strings.stagePerforming,
			strings.stageDdlGenerating
		];
		assert.ok(
			!others.includes(strings.stageReadingComposition),
			`${strings.code}: the reading shares another stage's words`
		);
	}
	assert.equal(ja.stageReadingComposition, '構図の読み中…');
	assert.equal(en.stageReadingComposition, 'Reading the composition…');
});

test('the laws stage names itself while it runs', () => {
	// The laws stage runs after the composition and before the commit, with no
	// layer event of its own either (stage B-5, 2026-10-20).
	for (const strings of [ja, en] as LangPack[]) {
		const laws = { action: 'choose_laws', attempt: 2, max_attempts: 4 };
		assert.equal(runningStageLabel(strings.stageInterpreting, laws, strings), strings.stageChoosingLaws);
		assert.equal(runningStageLabel(strings.stageDdlGenerating, laws, strings), strings.stageChoosingLaws);
		const others = [
			strings.stageSketching,
			strings.stageInterpreting,
			strings.stageStructuring(''),
			strings.stagePerforming,
			strings.stageDdlGenerating,
			strings.stageReadingComposition
		];
		assert.ok(!others.includes(strings.stageChoosingLaws), `${strings.code}: the laws stage shares another stage's words`);
	}
	assert.equal(ja.stageChoosingLaws, '法則の選択中…');
	assert.equal(en.stageChoosingLaws, 'Choosing the laws…');
});

test('the color stage names itself while it runs', () => {
	// The color stage runs after the laws stage and before the commit, with no
	// layer event of its own either (2026-10-20).
	for (const strings of [ja, en] as LangPack[]) {
		const colors = { action: 'choose_colors', attempt: 1, max_attempts: 4 };
		assert.equal(runningStageLabel(strings.stageInterpreting, colors, strings), strings.stageChoosingColors);
		assert.equal(runningStageLabel(strings.stageDdlGenerating, colors, strings), strings.stageChoosingColors);
		const others = [
			strings.stageSketching,
			strings.stageInterpreting,
			strings.stageStructuring(''),
			strings.stagePerforming,
			strings.stageDdlGenerating,
			strings.stageReadingComposition,
			strings.stageChoosingLaws
		];
		assert.ok(!others.includes(strings.stageChoosingColors), `${strings.code}: the color stage shares another stage's words`);
	}
	assert.equal(ja.stageChoosingColors, '配色の選択中…');
	assert.equal(en.stageChoosingColors, 'Choosing the colors…');
});
