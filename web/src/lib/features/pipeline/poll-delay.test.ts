import assert from 'node:assert/strict';
import test from 'node:test';
import { nextPollDelay } from './controller.ts';
import { stableCompletionWork } from '../ddl-editor/completion-range-states.ts';

test('unchanged completion work keeps its identity', () => {
	const stable = stableCompletionWork();
	const first = stable({ execution_id: 'one' });
	assert.equal(stable({ execution_id: 'one' }), first);
	assert.notEqual(stable({ history_id: 'one' }), first);
	assert.equal(stable(null), null);
});

test('polling backs off to two seconds and resets on a new sequence', () => {
	let delay = 250;
	for (const expected of [500, 1000, 2000, 2000]) {
		delay = nextPollDelay(delay, 'a', 'a');
		assert.equal(delay, expected);
	}
	assert.equal(nextPollDelay(delay, 'a', 'b'), 250);
});
