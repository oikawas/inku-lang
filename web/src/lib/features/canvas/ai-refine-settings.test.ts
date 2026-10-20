// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { DEFAULT_AI_REFINE_SETTINGS, parseAiRefineSettings } from './ai-refine-settings.ts';

test('the choices kept for the browser loop open the Server run with their generations as its moves', () => {
	// The colour and layout elements and the Vision direction left with the loop (2026-10-21).
	const kept = { generations: 8, color: true, layout: false, direction: '青を強く', mode: 'random' };
	assert.deepEqual(parseAiRefineSettings(JSON.stringify(kept)), { ...DEFAULT_AI_REFINE_SETTINGS, moves: 8 });
});

test('the run keeps its moves, its two moves and its direction', () => {
	const kept = { moves: 3, laws: false, juxtaposition: true, note: '夜の静けさへ' };
	assert.deepEqual(parseAiRefineSettings(JSON.stringify(kept)), kept);
	assert.equal(parseAiRefineSettings(JSON.stringify({ note: 'あ'.repeat(1200) })).note.length, 1000);
});

test('nothing kept, or something unreadable, opens with the defaults field by field', () => {
	assert.deepEqual(parseAiRefineSettings(null), DEFAULT_AI_REFINE_SETTINGS);
	assert.deepEqual(parseAiRefineSettings('{broken'), DEFAULT_AI_REFINE_SETTINGS);
	assert.deepEqual(parseAiRefineSettings('[1,2]'), DEFAULT_AI_REFINE_SETTINGS);
	assert.deepEqual(parseAiRefineSettings(JSON.stringify({ moves: 11, laws: 'no', note: 3 })), DEFAULT_AI_REFINE_SETTINGS);
	assert.equal(parseAiRefineSettings(JSON.stringify({ moves: 0 })).moves, 5);
	assert.equal(parseAiRefineSettings(JSON.stringify({ moves: 2.5 })).moves, 5);
});
