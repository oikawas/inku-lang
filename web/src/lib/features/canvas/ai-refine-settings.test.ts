// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { DEFAULT_AI_REFINE_SETTINGS, parseAiRefineSettings } from './ai-refine-settings.ts';

test('the autonomous refinement dialog drops retired variation choices and keeps the remaining choices', () => {
	const kept = {
		mode: 'vision', generations: 8, reading: false, color: true, layout: false, touch: true,
		direction: '青を強く'
	};
	assert.deepEqual(parseAiRefineSettings(JSON.stringify({ ...kept, variation: true, amplitude: 'large' })), kept);
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
