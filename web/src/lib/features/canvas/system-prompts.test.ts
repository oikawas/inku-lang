import assert from 'node:assert/strict';
import { test } from 'node:test';

import { loadSystemPrompts } from './system-prompts';

const sent = {
	system: 'work planner…',
	prompt_id: 'inku.typed-stage1-work-plan-prompt.v1',
	prompt_digest: 'abc',
	instruction_language: 'ja',
	attempt: 1
};

const answering = (status: number, body: unknown, paths: string[] = []) => async (path: string) => {
	paths.push(path);
	return new Response(JSON.stringify(body), { status });
};

test('the prompt tab tells a recorded prompt from an unrecorded or unreadable one', async () => {
	const paths: string[] = [];
	// A server from before 2026-10-13 names no stages: it kept Stage 1 and Stage 2.
	assert.deepEqual(
		await loadSystemPrompts('variation/1', answering(200, { recorded: true, stage1: sent, stage2: null }, paths)),
		{ state: 'recorded', stages: ['stage1', 'stage2'], catalog: null, image_catalog: null, image_ddl: null, image_review: null, sketch: null, reading: null, description_composition: null, description_ddl: null, description_review: null, stage1: sent, composition: null, laws: null, colors: null, stage2: null }
	);
	assert.deepEqual(paths, ['/api/pipeline/variations/variation%2F1/system-prompts']);
	assert.deepEqual(await loadSystemPrompts('v', answering(200, { recorded: false })), { state: 'not_recorded' });
	assert.deepEqual(await loadSystemPrompts(null, answering(200, {})), { state: 'not_recorded' });
	assert.deepEqual(await loadSystemPrompts('v', answering(404, {})), { state: 'unavailable' });
});

test('the sketch, the composition reading, the laws stage and the color stage come with what they were given, in the order a work calls them', async () => {
	const sketch = { ...sent, system: 'sketch…', prompt_id: 'inku.sketch-prompt.v1', message: '{"description":"一滴の墨"}' };
	const composition = {
		...sent,
		system: 'composition reader…',
		prompt_id: 'inku.composition-reading-prompt.v3',
		message: '記述:\n一滴の墨'
	};
	const laws = { ...sent, system: 'laws reader…', prompt_id: 'inku.laws-prompt.v1', message: '記述:\n一滴の墨' };
	const colors = { ...sent, system: 'colors reader…', prompt_id: 'inku.colors-prompt.v1', message: '## 記述\n一滴の墨' };
	const loaded = await loadSystemPrompts(
		'v',
		answering(200, {
			recorded: true,
			stages: ['stage2', 'colors', 'laws', 'composition', 'stage1', 'sketch'],
			sketch,
			stage1: sent,
			composition,
			laws,
			colors,
			stage2: null
		})
	);
	assert.deepEqual(loaded, {
		state: 'recorded',
		stages: ['sketch', 'stage1', 'composition', 'laws', 'colors', 'stage2'],
		catalog: null,
		image_catalog: null,
		image_ddl: null,
		image_review: null,
		sketch,
		reading: null,
		description_composition: null,
		description_ddl: null,
		description_review: null,
		stage1: sent,
		composition,
		laws,
		colors,
		stage2: null
	});
	// A work drawn before the laws stage and the color stage (2026-10-20) kept
	// no record of them.
	const earlier = await loadSystemPrompts(
		'v',
		answering(200, { recorded: true, stages: ['sketch', 'stage1', 'composition', 'stage2'], stage1: sent })
	);
	assert.equal(earlier.state === 'recorded' && earlier.stages.includes('laws'), false);
	assert.equal(earlier.state === 'recorded' && earlier.laws, null);
	assert.equal(earlier.state === 'recorded' && earlier.stages.includes('colors'), false);
	assert.equal(earlier.state === 'recorded' && earlier.colors, null);
	// A stage the record does not know stays out of the kept stages.
	const unknown = await loadSystemPrompts('v', answering(200, { recorded: true, stages: ['stage1', 'later'] }));
	assert.equal(unknown.state === 'recorded' && unknown.stages.join(), 'stage1');
	// The catalog choice and a picture's three are read and kept in call order (2026-10-26).
	const catalog = { ...sent, system: 'catalog chooser…', message: '記述: 一滴の墨' };
	const picture = { ...sent, system: 'picture writer…', message: '画像を読む' };
	const drawnFrom = await loadSystemPrompts(
		'v',
		answering(200, { recorded: true, stages: ['image_review', 'image_ddl', 'image_catalog', 'catalog'], catalog, image_ddl: picture })
	);
	assert.equal(drawnFrom.state === 'recorded' && drawnFrom.stages.join(), 'catalog,image_catalog,image_ddl,image_review');
	assert.deepEqual(drawnFrom.state === 'recorded' && [drawnFrom.catalog, drawnFrom.image_ddl, drawnFrom.image_review], [catalog, picture, null]);
});

test('a read-and-draw work shows its reading, its writing and its review, in the order it called them', async () => {
	const reading = { ...sent, system: 'reader…', prompt_id: 'inku.description-reading-prompt.v1', message: '{"description":"一滴の墨"}' };
	const writing = { ...sent, system: 'drawer…', prompt_id: 'inku.description-ddl-prompt.v1' };
	const review = { ...sent, system: 'reviewer…', prompt_id: 'inku.description-ddl-review-prompt.v1', attempt: 2 };
	const loaded = await loadSystemPrompts('v', answering(200, {
		recorded: true,
		stages: ['stage2', 'description_review', 'description_ddl', 'reading', 'stage1', 'sketch'],
		reading, description_ddl: writing, description_review: review,
	}));
	assert.equal(loaded.state, 'recorded');
	if (loaded.state !== 'recorded') return;
	assert.deepEqual(loaded.stages, ['sketch', 'reading', 'description_ddl', 'description_review', 'stage1', 'stage2']);
	assert.deepEqual([loaded.reading, loaded.description_ddl, loaded.description_review], [reading, writing, review]);
	assert.equal(loaded.stage1, null);
	assert.equal(loaded.description_composition, null);
});

test('with the composition and laws, they come between the reading and the writing', async () => {
	const composing = { ...sent, system: 'composer…', prompt_id: 'inku.description-composition-prompt.v1', message: '{"description":"一滴の墨"}' };
	const loaded = await loadSystemPrompts('v', answering(200, {
		recorded: true,
		stages: ['description_review', 'description_ddl', 'description_composition', 'reading'],
		reading: sent, description_composition: composing, description_ddl: sent, description_review: sent,
	}));
	assert.equal(loaded.state, 'recorded');
	if (loaded.state !== 'recorded') return;
	assert.deepEqual(loaded.stages, ['reading', 'description_composition', 'description_ddl', 'description_review']);
	assert.deepEqual(loaded.description_composition, composing);
});
