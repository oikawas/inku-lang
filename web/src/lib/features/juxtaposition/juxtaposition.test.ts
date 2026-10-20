// Run with: npm run test:unit  (node:test, no test dependency)
// How the sentence is joined is the shared core's rule (server/tests/data/juxtaposition-cases.json).
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { juxtapositionMetadata } from './juxtaposition.ts';

test('the child records the sentence its lineage leaves out next time', () => {
	// Failure: the record lacks the sentence, so the next juxtaposition down the lineage offers it again.
	const choice = {
		sentence: '廃駅に時刻表が残った。', reason: '待つ時間へ動く。', history_ids: ['w1', 'w2'], rank: 2, position: 0.25,
		joined: '夜の港。廃駅に時刻表が残った。'
	};
	assert.deepEqual(juxtapositionMetadata(choice, { choices: [choice], candidates: 549, model: 'chatgpt:gpt-6.1-sol' }), {
		juxtaposition: {
			sentence: '廃駅に時刻表が残った。', history_ids: ['w1', 'w2'], rank: 2, reason: '待つ時間へ動く。', position: 0.25,
			candidates: 549, model: 'chatgpt:gpt-6.1-sol'
		}
	});
});
