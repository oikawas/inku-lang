// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { dropFailedLine, planRetryRound, type BatchFailure } from './retry.ts';

function failure(line: number): BatchFailure {
	return { line, input: `line ${line}`, message: 'boom' };
}

test('a batch with no failures is not retried', () => {
	assert.equal(planRetryRound([], 0, 3, false), null);
});

test('the default of zero retries leaves the batch alone', () => {
	assert.equal(planRetryRound([failure(1)], 0, 0, false), null);
});

test('an interrupted batch is not retried even with rounds left', () => {
	assert.equal(planRetryRound([failure(1)], 0, 3, true), null);
});

test('the first round carries every failed line', () => {
	const round = planRetryRound([failure(2), failure(5)], 0, 1, false);
	assert.deepEqual(round, {
		round: 1,
		items: [failure(2), failure(5)],
	});
});

test('the round items are a copy, so the caller can mutate its own list', () => {
	const failures = [failure(1)];
	const round = planRetryRound(failures, 0, 1, false);
	assert.notEqual(round!.items, failures);
});

test('rounds stop at the configured limit', () => {
	// Drive the planner the way the batch loop does: a line that never succeeds
	// must be attempted exactly maxRetries times, and then the loop must end.
	for (const maxRetries of [1, 2, 3, 5]) {
		let failures = [failure(1)];
		let completedRounds = 0;
		const roundsSeen: number[] = [];
		for (let guard = 0; guard < 50; guard++) {
			const round = planRetryRound(failures, completedRounds, maxRetries, false);
			if (!round) break;
			roundsSeen.push(round.round);
			completedRounds += 1;
			failures = [failure(1)]; // still failing
		}
		assert.equal(
			roundsSeen.length,
			maxRetries,
			`maxRetries=${maxRetries} ran ${roundsSeen.length} rounds`,
		);
		assert.deepEqual(
			roundsSeen,
			Array.from({ length: maxRetries }, (_, i) => i + 1),
		);
	}
});

test('a line that succeeds on retry leaves the failure list', () => {
	const failures = [failure(1), failure(2), failure(3)];
	const after = dropFailedLine(failures, 2);
	assert.deepEqual(
		after.map((f) => f.line),
		[1, 3],
	);
});

test('the loop ends early once every line has succeeded', () => {
	let failures = [failure(1), failure(2)];
	let completedRounds = 0;
	let rounds = 0;
	for (let guard = 0; guard < 50; guard++) {
		const round = planRetryRound(failures, completedRounds, 5, false);
		if (!round) break;
		rounds += 1;
		completedRounds += 1;
		// One line recovers each round.
		failures = dropFailedLine(failures, round.items[0].line);
	}
	assert.equal(rounds, 2, 'stopped after the last line recovered, not at the limit');
	assert.deepEqual(failures, []);
});

test('an interrupt part-way through stops further rounds', () => {
	const failures = [failure(1)];
	assert.notEqual(planRetryRound(failures, 0, 3, false), null);
	assert.equal(planRetryRound(failures, 1, 3, true), null);
});
