import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
	DEFAULT_DRAW_ROUTE,
	droppedReadingLines,
	drawRouteLabel,
	drawRouteOf,
	readingStateNote,
	sketchModeForRoute,
} from './draw-route.ts';
import { paintStageLabel, runningStageLabel } from './paintStream.ts';
import { pipelineAttentionText } from './features/pipeline/attention.ts';
import { ja } from './i18n/ja.ts';
import { en } from './i18n/en.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

test('a description is drawn by the current stages unless the author chooses read and draw', () => {
	assert.equal(DEFAULT_DRAW_ROUTE, 'stages');
	assert.equal(drawRouteLabel('stages', true), '今の流れ');
	assert.equal(drawRouteLabel('read_and_draw', true), '読んで描く');
	assert.equal(drawRouteLabel('read_and_draw', false), 'Read and draw');
	// Read and draw starts with the sketch on; the current stages leave it as it is.
	assert.equal(sketchModeForRoute('read_and_draw', 'off'), 'on');
	assert.equal(sketchModeForRoute('stages', 'off'), 'off');
	assert.equal(sketchModeForRoute('stages', 'on'), 'on');
	// Neither the route nor the sketch is a stored setting.
	const work = read('./features/work/state.svelte.ts');
	assert.match(work, /let drawRoute = \$state<DrawRoute>\(DEFAULT_DRAW_ROUTE\)/);
	assert.match(work, /if \(route !== drawRoute\) sketchMode = sketchModeForRoute\(route, sketchMode\)/);
	assert.doesNotMatch(work, /persist\(\{[^}]*drawRoute/);
});

test('a work opened from the history sets the route it was drawn by', () => {
	assert.equal(drawRouteOf({ description_ddl: { reading_state: 'read' } }), 'read_and_draw');
	assert.equal(drawRouteOf({ description_ddl: null }), 'stages');
	assert.equal(drawRouteOf({}), 'stages');
	assert.equal(drawRouteOf(null), 'stages');
	// A run's view names its route; that wins over the record's absence.
	assert.equal(drawRouteOf({ route: 'read_and_draw' }), 'read_and_draw');
	assert.equal(drawRouteOf({ route: 'stages', description_ddl: {} }), 'stages');
	const page = read('../routes/+page.svelte');
	assert.match(page, /drawRouteOf\(it\)/);
	assert.match(page, /onSelectDrawRoute=\{work\.selectDrawRoute\}/);
});

test('every run asks for the route it was drawn with, the batch included', () => {
	const work = read('./features/work/state.svelte.ts');
	const currentWork = read('./features/run/current-work.ts');
	assert.match(work, /route: options\.route \?\? drawRoute/);
	assert.match(work, /const batchRoute = drawRoute/);
	assert.match(currentWork, /description: text,\s*route,/);
});

test('the progress names reading, writing, revising and reviewing in both languages', () => {
	for (const strings of [ja, en]) {
		const attempt = { action: 'read_description', attempt: 1, max_attempts: 2 };
		assert.equal(runningStageLabel('previous', attempt, strings), strings.readDrawReading);
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'write_description_ddl' }, strings), strings.readDrawWriting);
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'write_description_ddl', asked_again: true }, strings), strings.readDrawRevising);
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'review_description_ddl' }, strings), strings.readDrawReviewing);
		assert.equal(paintStageLabel('requested', strings, { sketchOn: true, readAndDraw: true }), strings.readDrawReading);
		assert.equal(paintStageLabel('requested', strings, { sketchOn: false, readAndDraw: true }), strings.readDrawWriting);
		assert.equal(paintStageLabel('score', strings, { sketchOn: true, readAndDraw: true }), strings.readDrawSaving);
		// The current stages keep their words.
		assert.equal(paintStageLabel('requested', strings, { sketchOn: false }), strings.stageInterpreting);
	}
	assert.equal(ja.readDrawReading, '記述を読んでいます…');
	assert.equal(ja.readDrawWriting, '指示書を書いています…');
	assert.equal(ja.readDrawRevising, '指示書を直しています…');
	assert.equal(ja.readDrawReviewing, '描いた画を見て直しています…');
	assert.equal(ja.readDrawSaving, '作品を保存しています…');
});

test('a read-and-draw run that stops says why, with the failure of its own requests', () => {
	for (const strings of [ja, en]) {
		for (const reason of ['description_ddl_failed', 'description_ddl_undrawable']) {
			const text = pipelineAttentionText(reason, null, strings);
			assert.ok(!text.endsWith(reason), `${reason} has no sentence`);
		}
		const timedOut = pipelineAttentionText('description_ddl_failed', { failure: 'transport_timeout', stage: 'read_and_draw', attempt: 2 }, strings);
		assert.ok(timedOut.length > pipelineAttentionText('description_ddl_failed', null, strings).length);
	}
});

test('the reading says what it did and what its anchor check dropped', () => {
	for (const state of ['read', 'supplied', 'fallback', 'off', 'pending']) {
		assert.ok(readingStateNote(state, true));
		assert.ok(readingStateNote(state, false));
	}
	assert.notEqual(readingStateNote('read', true), readingStateNote('fallback', true));
	assert.deepEqual(
		droppedReadingLines({
			dropped_items: [{ kind: 'texture', quote: 'つややかな衣', image: '光る布の面。' }],
			dropped_quotes: { speaker_seen_quote: '水に映る我' },
		}),
		['texture 「つややかな衣」 光る布の面。', 'speaker_seen_quote 「水に映る我」'],
	);
	assert.deepEqual(droppedReadingLines(null), []);
});
