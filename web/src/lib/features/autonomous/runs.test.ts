// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { runToResume, sharePercent, triesOf, type AutonomousRun } from './runs.ts';

function run(id: string, state: AutonomousRun['state'], turns: AutonomousRun['turns'] = []): AutonomousRun {
	return {
		id, history_id: 'work', state, stopping: false, turns, created_at: 1, updated_at: 1,
		settings: { moves: 5, kinds: ['laws', 'juxtaposition'], model: 'chatgpt:gpt-6-luna', language: 'ja' }
	};
}

test('a work opened again shows the run still going, not the last one that ended', () => {
	// Failure: the dialog offered a new run beside the one going on, which the Server refuses (409).
	assert.equal(runToResume([run('older-done', 'done'), run('going', 'running')])?.id, 'going');
	assert.equal(runToResume([run('stopped', 'stopped'), run('cut', 'interrupted')]), null);
});

test('the tries read in the order taken, each with its turn and its share in whole percent', () => {
	const taken = triesOf(run('r', 'done', [
		{ attempts: [{ attempt: 1, kind: 'juxtaposition', outcome: 'not_visible', share: 0.184 },
			{ attempt: 2, kind: 'laws', outcome: 'kept', share: 0.5 }] },
		{ attempts: [{ attempt: 1, kind: 'juxtaposition', outcome: 'unavailable', reason: 'description_locked' }] }
	]));
	assert.deepEqual(taken.map(({ turn, attempt }) => [turn, attempt.kind, attempt.outcome]), [
		[1, 'juxtaposition', 'not_visible'], [1, 'laws', 'kept'], [2, 'juxtaposition', 'unavailable']
	]);
	assert.deepEqual(taken.map(({ attempt }) => sharePercent(attempt.share)), ['18', '50', null]);
});
