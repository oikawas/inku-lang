import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import test from 'node:test';
import {
	DEFAULT_COMPOSITION_MODE,
	DEFAULT_DRAW_ROUTE,
	compositionColorsChangeLabel,
	compositionColorsChanges,
	compositionColorsStateNote,
	compositionFormLabel,
	compositionMeasureSummary,
	compositionModeOf,
	compositionOption,
	compositionPassed,
	compositionStateNote,
	droppedReadingLines,
	drawFlow,
	drawRouteLabel,
	drawRouteOf,
	drawSwitchLabel,
	readingStateNote,
	sketchModeForRoute,
} from './draw-route.ts';
import { paintStageLabel, runningStageLabel } from './paintStream.ts';
import { pipelineAttentionText } from './features/pipeline/attention.ts';
import { ja } from './i18n/ja.ts';
import { en } from './i18n/en.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

test('a description is drawn with a plan unless the author chooses in words', () => {
	assert.equal(DEFAULT_DRAW_ROUTE, 'stages');
	// The author's names (2026-10-27): by what the AI writes, not by a time.
	assert.equal(drawRouteLabel('stages', true), '型で描く');
	assert.equal(drawRouteLabel('read_and_draw', true), '言葉で描く');
	assert.equal(drawRouteLabel('stages', false), 'With a plan');
	assert.equal(drawRouteLabel('read_and_draw', false), 'In words');
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
	assert.match(work, /const route = options\.route \?\? drawRoute;\s*return \{\s*route,/);
	assert.match(work, /const batchRoute = drawRoute/);
	assert.match(currentWork, /description: text,\s*route,/);
	// The composition and laws travel with the route (2026-10-26): only read and draw sends it.
	assert.match(work, /\.\.\.compositionOption\(route, options\.compositionMode \?\? compositionMode\)/);
	assert.match(work, /const batchComposition = compositionMode/);
	assert.match(currentWork, /description: text,\s*route,\s*\.\.\.composition,/);
});

test('the composition and laws are sent only by read and draw, and a work says whether it had them', () => {
	assert.deepEqual(compositionOption('read_and_draw', 'on'), { composition: 'on' });
	assert.deepEqual(compositionOption('read_and_draw', 'off'), { composition: 'off' });
	assert.deepEqual(compositionOption('stages', 'on'), {});
	assert.equal(compositionModeOf({ description_ddl: { composition: { state: 'used' } } }), 'on');
	// A fallback was asked for the composition too; it redraws with it on.
	assert.equal(compositionModeOf({ description_ddl: { composition: { state: 'fallback', fallback: 'refused' } } }), 'on');
	assert.equal(compositionModeOf({ description_ddl: { reading_state: 'read' } }), 'off');
	assert.equal(compositionModeOf(null), DEFAULT_COMPOSITION_MODE);
	assert.equal(DEFAULT_COMPOSITION_MODE, 'off');
	// The stages always pass theirs, so the switch shows on there.
	assert.equal(compositionPassed('stages', 'off'), true);
	assert.equal(compositionPassed('read_and_draw', 'off'), false);
	assert.equal(compositionPassed('read_and_draw', 'on'), true);
	const page = read('../routes/+page.svelte');
	assert.match(page, /onSelectCompositionMode=\{work\.selectCompositionMode\}/);
	assert.match(page, /drawRouteOf\(it\),\s*compositionModeOf\(it\)\)/);
});

test('the last measure is counted and the pairs that did not fit are named', () => {
	const summary = compositionMeasureSummary({
		measures: [
			{ after: [{ law: 'B1', thing: 1, state: 'far' }] },
			{ after: [{ law: 'B1', thing: 1, state: 'fitted' }, { law: 'B9', thing: 2, state: 'ok' }, { law: 'C1', thing: 3, state: 'off' },
				{ law: 'B21', thing: 1, state: 'not_measured' }] },
		],
	});
	assert.deepEqual(summary.counts, [['fitted', 1], ['ok', 1], ['off', 1], ['not_measured', 1]]);
	// The hand the writer draws is not measured, so it is not a pair that missed.
	assert.deepEqual(summary.misses, [{ law: 'C1', thing: '3', state: 'off' }]);
	assert.equal(compositionStateNote({ state: 'fallback', fallback: 'transport_timeout' }, true),
		'構図と法則を決められず、構図と法則なしで書いた（transport_timeout）');
	assert.equal(compositionFormLabel('one_corner', true), '一角');
	assert.equal(compositionFormLabel('a_new_form', true), 'a_new_form');
});

test('the colors chosen after the review are counted by how each line was written', () => {
	const colors = { state: 'used' as const, main_law: 'D5', laws: ['D5'], ground: 'black', changes: [
		{ line: 2, how: 'color_word', before: 'a', after: ['b'] },
		{ line: 1, how: 'ground', before: 'c', after: ['d'] },
		{ line: 3, how: 'color_word', before: 'e', after: ['f'] },
	] };
	assert.deepEqual(compositionColorsChanges(colors), [['color_word', 2], ['ground', 1]]);
	assert.equal(compositionColorsChangeLabel('ground_added', true), '背景の文を足した');
	assert.equal(compositionColorsStateNote(colors, true), '配色を選び、当てて確定した');
	assert.equal(compositionColorsStateNote({ state: 'fallback', fallback: 'compile' }, true),
		'配色を当てられず、配色の前の指示書で確定した（compile）');
	assert.equal(compositionColorsChanges(null).length, 0);
});

test('the flow under the switches names the steps a run passes, in their order', () => {
	const labels = (route: 'stages' | 'read_and_draw', sketch: 'on' | 'off', composition: 'on' | 'off') =>
		drawFlow(route, sketch, composition, true).map((step) => step.label).join(' › ');
	// The stages pass the composition and laws and the colors after the plan, whatever the switch says.
	assert.equal(labels('stages', 'off', 'off'), '記述 › 型を埋める › 構図と法則 › 配色 › 画');
	assert.equal(labels('stages', 'on', 'on'), '記述 › 写生 › 型を埋める › 構図と法則 › 配色 › 画');
	// In words decides the composition and laws before it writes, and their colors end it.
	assert.equal(labels('read_and_draw', 'on', 'off'), '記述 › 写生 › 言葉で書く › 見て直す › 画');
	assert.equal(labels('read_and_draw', 'on', 'on'), '記述 › 写生 › 構図と法則 › 言葉で書く › 見て直す › 配色 › 画');
	// A step a switch put there is marked so; the stages' own steps are not.
	const kinds = drawFlow('read_and_draw', 'on', 'on', false).map((step) => `${step.label}:${step.kind}`);
	assert.deepEqual(kinds, ['Description:end', 'Sketch:switch', 'Composition and laws:switch', 'Write in words:fixed',
		'Look and correct:fixed', 'Colors:switch', 'Picture:end']);
	assert.ok(drawFlow('stages', 'off', 'on', true).every((step) => step.kind !== 'switch'));
});

test('the switches keep their names on both routes, and the panel shows them as one block', () => {
	assert.equal(drawSwitchLabel('sketch', true), '写生');
	assert.equal(drawSwitchLabel('composition', true), '構図と法則');
	const panel = read('./components/InputPanel.svelte');
	assert.match(panel, /<DrawConditions route=\{drawRoute\} \{sketchMode\} \{compositionMode\} \{isJapanese\}/);
	assert.doesNotMatch(panel, /RouteSelect|CompositionSelect|SketchSelect/);
	const block = read('./components/DrawConditions.svelte');
	// The composition switch is locked on the stages, never hidden or disabled.
	assert.match(block, /on=\{compositionOn\} locked=\{compositionLocked\}/);
	assert.match(block, /const compositionLocked = \$derived\(route === 'stages'\)/);
	assert.doesNotMatch(block, /\{#if route === 'read_and_draw'\}/);
});

test('the progress names reading, writing, revising and reviewing in both languages', () => {
	for (const strings of [ja, en]) {
		const attempt = { action: 'read_description', attempt: 1, max_attempts: 2 };
		assert.equal(runningStageLabel('previous', attempt, strings), strings.readDrawReading);
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'write_description_ddl' }, strings), strings.readDrawWriting);
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'write_description_ddl', asked_again: true }, strings), strings.readDrawRevising);
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'review_description_ddl' }, strings), strings.readDrawReviewing);
		// The composition and laws, and their asking again (2026-10-26).
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'compose_description' }, strings), strings.readDrawComposing);
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'compose_description', asked_again: true }, strings), strings.readDrawRecomposing);
		// The colors after the review say what the current stages' colors say.
		assert.equal(runningStageLabel('previous', { ...attempt, action: 'choose_colors' }, strings), strings.stageChoosingColors);
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
	assert.equal(ja.readDrawComposing, '構図と法則を決めています…');
	assert.equal(ja.readDrawRecomposing, '構図と法則を決め直しています…');
	assert.equal(en.readDrawComposing, 'Deciding the composition and laws…');
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
