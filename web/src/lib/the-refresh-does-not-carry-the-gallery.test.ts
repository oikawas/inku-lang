// Run with: npm run test:unit  (node:test, no test dependency)
//
// Contract 3. The twelve-second refresh asks whether the listing changed before
// it fetches the listing, and the two events that mean "the user came back to
// the tab" no longer jump the five-second floor.
//
// The decisions live in `historyRefreshDecision.ts` so these can drive them.
// But a decision the page does not call is a decision that measures nothing --
// extracting a function does not move the thoroughfare -- so every behavioural
// check here has a companion that reads `+page.svelte` and confirms the page
// still goes through it. Removing the call in the page and neutering the
// function are different perturbations, and each must turn something red.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import {
	historyRefreshBlockedBy,
	historyStripIsCurrent,
	type HistoryRefreshConditions
} from './historyRefreshDecision.ts';

const PAGE_SOURCE = readFileSync(
	fileURLToPath(new URL('../routes/+page.svelte', import.meta.url)),
	'utf-8'
);

/** The body of one function in the page, braces matched. */
function functionBody(source: string, signature: string): string {
	const start = source.indexOf(signature);
	assert.notEqual(start, -1, `${signature} is gone from +page.svelte`);
	let depth = 0;
	for (let i = source.indexOf('{', start); i < source.length; i += 1) {
		if (source[i] === '{') depth += 1;
		else if (source[i] === '}') {
			depth -= 1;
			if (depth === 0) return source.slice(start, i + 1);
		}
	}
	throw new Error(`${signature} never closes`);
}

// Sliced rather than searched whole: a structural claim about this function is
// satisfied by any other occurrence in a 7,000-line file if it is not fenced in.
// Matched without the closing paren so that restoring the parameter still
// slices the function rather than aborting the file. What the parameter list
// holds is T-7's business, and it says so by name.
const REFRESH = functionBody(PAGE_SOURCE, 'async function refreshHistoryForExternalSave(');
const MOUNT = functionBody(PAGE_SOURCE, 'onMount(() =>');

const NOTHING_IN_THE_WAY: HistoryRefreshConditions = {
	signedIn: true,
	managerOpen: false,
	starredOnly: false,
	offset: 0,
	loading: false,
	visible: true,
	inFlight: false,
	now: 100_000,
	lastRefreshAt: 0,
	minGapMs: 5000
};

const HELD = { total: 21, newestAt: 1_700_000_000_000, newestId: 'work-a' };
const SAME = { total: 21, newest_at: 1_700_000_000_000, newest_id: 'work-a' };

// ── T-1: nothing changed, so the gallery stays where it is ──────────────────

test('T-1 an unchanged answer means the listing is not fetched', () => {
	assert.equal(historyStripIsCurrent(SAME, HELD), true);
	// Round after round, as the poll actually runs: the answer never moves and
	// the decision never flips.
	for (let round = 0; round < 5; round += 1) {
		assert.equal(historyStripIsCurrent({ ...SAME }, { ...HELD }), true);
	}
});

test('T-1 the page asks the cheap question before it fetches the listing', () => {
	// The wiring half. Without this, deleting the early return from the page
	// leaves every behavioural check above still green.
	const asked = REFRESH.indexOf('fetchHistoryState()');
	const decided = REFRESH.indexOf('historyStripIsCurrent(');
	const fetched = REFRESH.indexOf('fetchHistoryOffset(');
	assert.notEqual(asked, -1, 'the refresh no longer asks /api/history/state');
	assert.notEqual(decided, -1, 'the refresh no longer consults the decision');
	assert.notEqual(fetched, -1, 'the refresh no longer fetches the listing at all');
	assert.ok(asked < fetched, 'the state is asked for after the listing, which saves nothing');
	assert.ok(decided < fetched, 'the decision is made after the listing is already fetched');
	// It must be an early return, not a value computed and thrown away.
	assert.match(
		REFRESH,
		/if \(state && historyStripIsCurrent\([^)]*\{[^}]*\}\)\) return;/s,
		'the decision no longer stops the round'
	);
	// The strip is what it compares against, so it needs the strip's numbers.
	assert.match(REFRESH, /total: historyTotal/);
	assert.match(REFRESH, /newestId: historyItems\[0\]\?\.id \?\? null/);
	assert.match(REFRESH, /newestAt: historyItems\[0\]\?\.at \?\? null/);
});

// ── T-2: something changed, so it is fetched ────────────────────────────────

test('T-2 each of the three quantities on its own means the listing is stale', () => {
	// Named one at a time. A decision that answered "changed" only when all
	// three moved would pass a test that moved all three.
	assert.equal(historyStripIsCurrent({ ...SAME, total: 22 }, HELD), false, 'a work appeared');
	assert.equal(
		historyStripIsCurrent({ ...SAME, newest_at: SAME.newest_at + 1 }, HELD),
		false,
		'a newer work was saved'
	);
	assert.equal(
		historyStripIsCurrent({ ...SAME, newest_id: 'work-b' }, HELD),
		false,
		'a different work is newest'
	);
});

test('T-2 an empty gallery and a first save are both handled', () => {
	const empty = { total: 0, newestAt: null, newestId: null };
	assert.equal(historyStripIsCurrent({ total: 0, newest_at: null, newest_id: null }, empty), true);
	assert.equal(
		historyStripIsCurrent({ total: 1, newest_at: 5, newest_id: 'first' }, empty),
		false,
		'the very first work must reach the strip'
	);
});

test('T-2 an answer that did not arrive falls through and fetches', () => {
	// The safe direction: a server that cannot answer costs bandwidth, a client
	// that treats silence as "nothing changed" costs the user their work
	// appearing at all.
	assert.match(REFRESH, /const state = await fetchHistoryState\(\);/);
	assert.match(REFRESH, /if \(state && /, 'a missing answer must not count as unchanged');
});

// ── T-3: the client half of two saves inside one millisecond ────────────────

test('T-3 two works sharing a millisecond are told apart', () => {
	// `newest_at` is identical; only the id moved. The server half of this is
	// in test_the_refresh_does_not_carry_the_gallery.py.
	assert.equal(
		historyStripIsCurrent({ ...SAME, newest_id: 'work-b' }, HELD),
		false,
		'the second save inside one millisecond went unnoticed'
	);
});

// ── T-6: the guards that were already there are still there ─────────────────

test('T-6 the four conditions each stop the round before it asks anything', () => {
	const CASES: Array<[string, Partial<HistoryRefreshConditions>, string]> = [
		['manager-open', { managerOpen: true }, 'the manager is showing the same works'],
		['starred-only', { starredOnly: true }, 'the strip is filtered'],
		['not-the-first-page', { offset: 21 }, 'the strip is not on the first page'],
		['tab-hidden', { visible: false }, 'the tab is in the background']
	];
	for (const [reason, condition, why] of CASES) {
		assert.equal(
			historyRefreshBlockedBy({ ...NOTHING_IN_THE_WAY, ...condition }),
			reason,
			`the round ran when ${why}`
		);
	}
	// The other three that were already in place, so that dropping one of them
	// is a failure too.
	assert.equal(historyRefreshBlockedBy({ ...NOTHING_IN_THE_WAY, signedIn: false }), 'signed-out');
	assert.equal(historyRefreshBlockedBy({ ...NOTHING_IN_THE_WAY, loading: true }), 'drawing');
	assert.equal(historyRefreshBlockedBy({ ...NOTHING_IN_THE_WAY, inFlight: true }), 'already-asking');
	// And with nothing in the way it does run, or the check above is satisfied
	// by a function that blocks everything.
	assert.equal(historyRefreshBlockedBy(NOTHING_IN_THE_WAY), null);
});

test('T-6 the page hands the guards its live values', () => {
	// A guard fed a constant is a guard that never fires. Each of these names
	// the page's own state.
	assert.match(REFRESH, /signedIn: !!authToken/);
	assert.match(REFRESH, /managerOpen: historyManager\.open/);
	assert.match(REFRESH, /starredOnly: historyStarredOnly/);
	assert.match(REFRESH, /offset: historyOffset/);
	assert.match(REFRESH, /loading,/);
	assert.match(REFRESH, /visible: document\.visibilityState === 'visible'/);
	assert.match(REFRESH, /inFlight: externalHistoryRefreshInFlight/);
	assert.match(REFRESH, /lastRefreshAt: lastExternalHistoryRefreshAt/);
	assert.match(REFRESH, /minGapMs: EXTERNAL_HISTORY_REFRESH_MIN_GAP_MS/);
	assert.match(REFRESH, /if \(historyRefreshBlockedBy\(\{[^}]*\}\)\) return;/s);
	// The page must hold no second copy of the guards, or removing one from the
	// module changes nothing.
	assert.equal(REFRESH.includes('document.visibilityState !== '), false);
	assert.equal(REFRESH.includes('historyOffset !== 0'), false);
});

// ── T-7: coming back to the tab no longer jumps the floor ───────────────────

test('T-7 five focus events one second apart run once', () => {
	// What the measurement caught on 2026-08-11: two rounds 2.5 seconds apart
	// with a five second floor in force, because focus was forced.
	let lastRefreshAt = 0;
	let ran = 0;
	for (const now of [1000, 2000, 3000, 4000, 5000]) {
		if (historyRefreshBlockedBy({ ...NOTHING_IN_THE_WAY, now, lastRefreshAt })) continue;
		ran += 1;
		lastRefreshAt = now;
	}
	assert.equal(ran, 1, `five focus events one second apart ran ${ran} rounds`);
});

test('T-7 no caller can ask the floor to be skipped', () => {
	// Driven with the escape hatch that used to exist. Restoring `!force &&`
	// inside the decision turns this red; restoring the parameter on the page
	// turns the companion below red.
	const forced = { ...NOTHING_IN_THE_WAY, now: 1000, lastRefreshAt: 0, force: true };
	assert.equal(
		historyRefreshBlockedBy(forced as HistoryRefreshConditions),
		'too-soon',
		'a caller got past the floor'
	);
});

test('T-7 the page calls the refresh with nothing to force', () => {
	assert.match(PAGE_SOURCE, /async function refreshHistoryForExternalSave\(\): Promise<void>/);
	const calls = PAGE_SOURCE.match(/refreshHistoryForExternalSave\([^)]*\)/g) ?? [];
	assert.ok(calls.length >= 3, `expected the timer and both handlers, found ${calls.length}`);
	for (const call of calls) {
		assert.equal(call, 'refreshHistoryForExternalSave()', `${call} still forces the round`);
	}
});

// ── T-8: coming back to the tab still refreshes ─────────────────────────────

test('T-8 a focus past the floor does run', () => {
	// The other half of T-7. Without this, "never run at all" would pass.
	assert.equal(
		historyRefreshBlockedBy({ ...NOTHING_IN_THE_WAY, now: 6000, lastRefreshAt: 0 }),
		null,
		'a focus well past the floor was refused'
	);
	// Exactly at the floor counts as past it.
	assert.equal(
		historyRefreshBlockedBy({ ...NOTHING_IN_THE_WAY, now: 5000, lastRefreshAt: 0 }),
		null
	);
});

test('T-8 the page still listens for the tab coming back', () => {
	// The behaviour the floor fix must not take with it. Deleting either
	// listener means a work saved elsewhere waits up to twelve seconds after
	// the user is already looking at the strip.
	assert.match(MOUNT, /document\.addEventListener\('visibilitychange', onHistoryVisibilityChange\)/);
	assert.match(MOUNT, /window\.addEventListener\('focus', onHistoryWindowFocus\)/);
	assert.match(
		MOUNT,
		/function onHistoryVisibilityChange\(\) \{\s*if \(document\.visibilityState === 'visible'\) void refreshHistoryForExternalSave\(\);\s*\}/
	);
	assert.match(
		MOUNT,
		/function onHistoryWindowFocus\(\) \{\s*void refreshHistoryForExternalSave\(\);\s*\}/
	);
	// And the twelve-second timer is untouched: the contract changes what a
	// round costs, not how often one happens.
	assert.match(MOUNT, /window\.setInterval\(\(\) => \{\s*void refreshHistoryForExternalSave\(\);\s*\}, EXTERNAL_HISTORY_REFRESH_MS\)/);
});
