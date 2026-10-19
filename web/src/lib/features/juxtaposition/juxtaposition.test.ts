// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { joinJuxtaposition, juxtapositionMetadata } from './juxtaposition.ts';

test('the sentence follows a stop, and a description without one gets it', () => {
	// Failure: the two texts run together ("…竜田川廃駅に…"), and Stage 1 reads them as one clause.
	assert.equal(joinJuxtaposition('夜の港で、灯台の光が波を数えていた。', '廃駅に時刻表が残った。'), '夜の港で、灯台の光が波を数えていた。廃駅に時刻表が残った。');
	assert.equal(joinJuxtaposition('ちはやぶる　神代も聞かず　竜田川 ', '廃駅に時刻表が残った。'), 'ちはやぶる　神代も聞かず　竜田川。廃駅に時刻表が残った。');
	assert.equal(joinJuxtaposition('A quiet harbour', 'A train never came.'), 'A quiet harbour. A train never came.');
	assert.equal(joinJuxtaposition('A quiet harbour.', 'A train never came.'), 'A quiet harbour. A train never came.');
});

test('the child records the sentence its lineage leaves out next time', () => {
	// Failure: the record lacks the sentence, so the next juxtaposition down the lineage offers it again.
	const choice = { sentence: '廃駅に時刻表が残った。', reason: '待つ時間へ動く。', history_ids: ['w1', 'w2'], rank: 2, position: 0.25 };
	assert.deepEqual(juxtapositionMetadata(choice, { choices: [choice], candidates: 549, model: 'chatgpt:gpt-6.1-sol' }), {
		juxtaposition: {
			sentence: '廃駅に時刻表が残った。', history_ids: ['w1', 'w2'], rank: 2, reason: '待つ時間へ動く。', position: 0.25,
			candidates: 549, model: 'chatgpt:gpt-6.1-sol'
		}
	});
});
