import assert from 'node:assert/strict';
import { test } from 'node:test';

const identity = <T>(value: T): T => value;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = identity;

const { RefinementSessionState } = await import('./refinement-session.svelte.ts');

type FakeCandidate = {
	id: string;
	label: string;
	selected: boolean;
	saved?: boolean;
	result: Record<string, unknown>;
};

function fakeElapsed() {
	return {
		ms: 0,
		starts: 0,
		stops: 0,
		start() { this.starts += 1; this.ms = 0; },
		stop() { this.stops += 1; }
	};
}

function candidate(id: string): FakeCandidate {
	return { id, label: id, selected: false, result: {} };
}

test('T-308: single and grid sessions own busy, elapsed, and initial progress', () => {
	const elapsed = fakeElapsed();
	const session = new RefinementSessionState(elapsed);
	session.beginSingle();
	assert.equal(session.busy, true);
	assert.deepEqual([session.tokensIn, session.tokensOut, elapsed.starts], [null, null, 1]);
	session.finishSingle();
	assert.equal(session.busy, false);
	assert.equal(elapsed.stops, 1);

	const controller = session.beginGrid({ includesReading: true, taskLabel: 'reading', count: 4 });
	assert.equal(session.gridBusy, true);
	assert.equal(session.gridCanAbort, false);
	assert.equal(session.gridIncludesReading, true);
	assert.equal(session.gridTaskLabel, 'reading');
	assert.deepEqual(session.gridSlots, ['waiting', 'waiting', 'waiting', 'waiting']);
	assert.deepEqual(session.gridSlotLabels, ['', '', '', '']);
	assert.deepEqual([session.gridDone, session.gridTotal], [0, 4]);
	assert.equal(session.isActive(controller), true);
});

test('T-309/T-310: only the active controller can move slots or settle the grid', () => {
	const elapsed = fakeElapsed();
	const session = new RefinementSessionState(elapsed);
	const active = session.beginGrid({ includesReading: false, taskLabel: 'layout', count: 2 });
	const stale = new AbortController();

	assert.equal(session.enableAbort(stale), false);
	assert.equal(session.setPlans(stale, ['old', 'old']), false);
	assert.equal(session.setPlans(active, ['one', 'two']), true);
	assert.equal(session.enableAbort(active), true);
	assert.equal(session.seatSlot(active, 1, 'running'), true);
	assert.equal(session.finishSlot(active, 1), true);
	assert.deepEqual(session.gridSlots, ['waiting', 'done']);
	assert.equal(session.gridDone, 1);

	const items = [candidate('a'), candidate('b')];
	assert.equal(session.commitCandidates(stale, items as never[]), false);
	assert.equal(session.commitCandidates(active, items as never[]), true);
	assert.equal(session.addTokens(active, 5, 7), true);
	assert.deepEqual([session.tokensIn, session.tokensOut], [5, 7]);
	assert.equal(session.failGrid(stale, 'stale'), false);
	assert.equal(session.failGrid(active, 'kept'), true);
	assert.equal(session.status, 'kept');
	assert.equal(session.finishGrid(stale), false);
	assert.equal(session.gridBusy, true);
	assert.equal(session.finishGrid(active), true);
	assert.equal(session.gridBusy, false);
	assert.equal(elapsed.stops, 1);
});

test('T-309: target reset aborts and invalidates the active grid', () => {
	const session = new RefinementSessionState(fakeElapsed());
	const controller = session.beginGrid({ includesReading: false, taskLabel: 'color', count: 1 });
	session.enableAbort(controller);
	session.reset();
	assert.equal(controller.signal.aborted, true);
	assert.equal(session.isActive(controller), false);
	assert.equal(session.gridBusy, false);
	assert.equal(session.gridCanAbort, false);
	assert.deepEqual(session.candidates, []);
	assert.deepEqual(session.gridSlots, []);
	assert.equal(session.status, null);
});

test('T-311: selection, saved projection, and save lock stay in the session owner', () => {
	const session = new RefinementSessionState(fakeElapsed());
	const controller = session.beginGrid({ includesReading: false, taskLabel: 'layout', count: 1 });
	session.commitCandidates(controller, [candidate('a'), candidate('b')] as never[]);
	session.finishGrid(controller);
	session.toggleCandidate('a');
	assert.equal(session.candidates[0]?.selected, true);

	session.beginSave();
	assert.equal(session.gridBusy, true);
	assert.equal(session.status, null);
	session.markSaved('a');
	assert.deepEqual(
		[session.candidates[0]?.saved, session.candidates[0]?.selected],
		[true, false]
	);
	session.finishSave();
	assert.equal(session.gridBusy, false);

	session.reset({ preserveCandidates: true });
	assert.equal(session.candidates.length, 2);
});
