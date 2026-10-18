// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { DEFAULT_AI_REFINE_SETTINGS, parseAiRefineSettings } from './ai-refine-settings.ts';

test('the autonomous refinement dialog drops retired variation choices and keeps the remaining choices', () => {
	const kept = {
		generations: 8, color: true, layout: false,
		direction: '青を強く'
	};
	// The touch and the reading were removed (2026-10-14); a choice kept from before is dropped like the others.
	assert.deepEqual(parseAiRefineSettings(JSON.stringify({ ...kept, variation: true, amplitude: 'large', touch: true, reading: false })), kept);
});

test('a method kept from before random refinement was removed is dropped (the author, 2026-10-18)', () => {
	const kept = { generations: 3, color: true, layout: true, direction: '' };
	assert.deepEqual(parseAiRefineSettings(JSON.stringify({ ...kept, mode: 'random' })), kept);
	assert.deepEqual(parseAiRefineSettings(JSON.stringify({ ...kept, mode: 'vision' })), kept);
	assert.equal('mode' in DEFAULT_AI_REFINE_SETTINGS, false);
});

test('nothing kept, or something unreadable, opens with the defaults field by field', () => {
	assert.deepEqual(parseAiRefineSettings(null), DEFAULT_AI_REFINE_SETTINGS);
	assert.deepEqual(parseAiRefineSettings('{broken'), DEFAULT_AI_REFINE_SETTINGS);
	assert.deepEqual(parseAiRefineSettings('[1,2]'), DEFAULT_AI_REFINE_SETTINGS);
	const partly = parseAiRefineSettings(JSON.stringify({ mode: 'other', generations: 11, reading: 'no', amplitude: 'small' }));
	assert.deepEqual(partly, DEFAULT_AI_REFINE_SETTINGS);
	assert.equal(parseAiRefineSettings(JSON.stringify({ generations: 0 })).generations, 5);
	assert.equal(parseAiRefineSettings(JSON.stringify({ generations: 2.5 })).generations, 5);
});
