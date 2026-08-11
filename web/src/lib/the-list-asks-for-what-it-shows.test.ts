// Run with: npm run test:unit  (node:test, no test dependency)
//
// The first load used to ask for the history manager's page size instead of the
// strip's -- 65 works where 21 are shown, 50.5 MB where 23.5 MB would do, on
// every visit, for a modal that was usually never opened. These are the gates
// for moving that cost onto whoever opens the manager.
//
// T-3..T-6 drive the real HistoryManagerState rather than reading its source,
// so that renaming a field or rewriting a condition cannot keep them green.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { historyListLimit } from './historyListLimit.ts';
// The rune shim, the fake manager and the stand-in for $derived live in the
// harness so that contract 2's gates next door drive the same ones.
import {
	MANAGER_PAGE_SIZE,
	MEASURED_PAGE_SIZE,
	STRIP_SIZE,
	TOTAL,
	makeManager,
	refreshDerived,
	works
} from './history-manager-harness.ts';

// ── T-1 ─────────────────────────────────────────────────────────────────────
test('the first load asks for what the strip shows, not for a manager page', () => {
	assert.equal(
		historyListLimit({
			anchorId: null,
			offset: 0,
			starredOnly: false,
			windowSize: STRIP_SIZE,
			managerPageSize: MANAGER_PAGE_SIZE
		}),
		STRIP_SIZE
	);
	// Stated separately so that returning the manager's page size cannot pass by
	// the two numbers happening to be equal.
	assert.notEqual(STRIP_SIZE, MANAGER_PAGE_SIZE);
});

// ── The wiring ──────────────────────────────────────────────────────────────
// Not one of the contract's gates. Measured after writing them: putting the old
// ternary back into +page.svelte restores the whole 50 MB defect and turns
// nothing red, because every gate above drives the extracted function and no
// gate watches the road to it. Extraction does not move the thoroughfare. This
// reads the page's source, the way the trash-view gate next door does, since
// `test:unit` is node --test with no DOM to render the component in.
const PAGE_SOURCE = readFileSync(
	fileURLToPath(new URL('../routes/+page.svelte', import.meta.url)),
	'utf-8'
);

test('the page asks the shared decision instead of deciding again inline', () => {
	const assignments = [...PAGE_SOURCE.matchAll(/const listLimit = ([^;]*);/g)];
	assert.equal(assignments.length, 1, 'expected exactly one listLimit assignment');
	assert.match(assignments[0][1], /^historyListLimit\(/);
});

// ── T-2 ─────────────────────────────────────────────────────────────────────
test('the three routes that already asked for the strip size still do', () => {
	const routes = [
		{ name: 'anchored', anchorId: 'some-work', offset: 0, starredOnly: false },
		{ name: 'paged', anchorId: null, offset: 40, starredOnly: false },
		{ name: 'starred', anchorId: null, offset: 0, starredOnly: true }
	];
	for (const route of routes) {
		assert.equal(
			historyListLimit({
				anchorId: route.anchorId,
				offset: route.offset,
				starredOnly: route.starredOnly,
				windowSize: STRIP_SIZE,
				managerPageSize: MANAGER_PAGE_SIZE
			}),
			STRIP_SIZE,
			`route ${route.name}`
		);
	}
});

// ── T-3 ─────────────────────────────────────────────────────────────────────
test("the manager's page does not shrink to the strip's handful", () => {
	const { manager } = makeManager([], TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	assert.equal(manager.pageSize, MANAGER_PAGE_SIZE);
	assert.equal(manager.activeItems.length, STRIP_SIZE);
});

// ── T-4 ─────────────────────────────────────────────────────────────────────
test('holding the strip is not claimed to be holding a page', async () => {
	const { manager } = makeManager([], TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerived(manager);
	assert.equal(
		manager.preloadMatches('active', 0, manager.pageSize, '', false, false, TOTAL),
		false
	);

	// The case above is also refused by the count of works in hand (21 < 65), so
	// on its own it cannot see the claim being made. This one can: a page has
	// been fetched, then one new work is drawn and the strip seeds a shorter but
	// fresher list. The works in hand are still a page's worth, so whether the
	// manager believes it is holding the current page rests on the claim alone --
	// and believing it here would open the manager without the new work in it.
	const stale = makeManager(works(MANAGER_PAGE_SIZE, 'page'), TOTAL);
	stale.manager.pageSize = MANAGER_PAGE_SIZE;
	await stale.manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE });
	refreshDerived(stale.manager);
	stale.manager.seedFromStrip(works(STRIP_SIZE, 'fresh'), TOTAL + 1, 6, MANAGER_PAGE_SIZE);
	refreshDerived(stale.manager);
	assert.equal(stale.manager.items.length, MANAGER_PAGE_SIZE);
	assert.equal(
		stale.manager.preloadMatches('active', 0, MANAGER_PAGE_SIZE, '', false, false, TOTAL + 1),
		false
	);
});

// ── T-5 ─────────────────────────────────────────────────────────────────────
test('opening the manager without a page in hand fetches one', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerived(manager);
	assert.equal(calls.length, 0);

	manager.openWith(works(STRIP_SIZE), TOTAL, 6);

	assert.equal(calls.length, 1);
	const asked = new URL(calls[0], 'http://localhost');
	assert.equal(asked.searchParams.get('offset'), '0');
	assert.equal(asked.searchParams.get('limit'), String(MANAGER_PAGE_SIZE));
	// The seeded works stay on screen while the page is on its way.
	assert.equal(manager.activeItems.length, STRIP_SIZE);

	// And the same stale-page case as T-4, from the other side: seeding after a
	// page is in hand must leave opening the manager costing a fetch, because
	// the page in hand is one work out of date.
	const stale = makeManager(works(MANAGER_PAGE_SIZE, 'page'), TOTAL);
	stale.manager.pageSize = MANAGER_PAGE_SIZE;
	await stale.manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE });
	refreshDerived(stale.manager);
	stale.manager.seedFromStrip(works(STRIP_SIZE, 'fresh'), TOTAL + 1, 6, MANAGER_PAGE_SIZE);
	refreshDerived(stale.manager);
	assert.equal(stale.calls.length, 1);

	stale.manager.openWith(works(STRIP_SIZE, 'fresh'), TOTAL + 1, 6);

	assert.equal(stale.calls.length, 2);
});

// ── One click, one request ──────────────────────────────────────────────────
// Beyond the contract's gates, from the author's ruling of 2026-08-11: pressing
// the history button fetches once. Measured in the browser first -- opening the
// manager sent two identical requests a millisecond apart, 105.9 MB for one
// click, because the page's search effect re-runs on open and asked for the
// same page that openWith had just asked for.
test('two callers wanting the same page at once cost one request', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.pageSize = MANAGER_PAGE_SIZE;

	const both = Promise.all([
		manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE }),
		manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE })
	]);
	assert.equal(calls.length, 1);
	await both;

	// And once it is back, asking again is a real question, not a duplicate.
	await manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE });
	assert.equal(calls.length, 2);
});

// The sequence one press actually produces, measured in the browser: the page
// opens the manager with a guessed page size, then the modal appears, measures
// its own grid and reports a smaller one. Asking again for the smaller page
// cost a second 46 MB for works that were already on their way.
test('the modal measuring itself smaller does not cost a second page', () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerived(manager);

	manager.openWith(works(STRIP_SIZE), TOTAL, 6);
	refreshDerived(manager);
	assert.equal(calls.length, 1);
	assert.equal(new URL(calls[0], 'http://x').searchParams.get('limit'), String(MANAGER_PAGE_SIZE));

	manager.setPageSize(MEASURED_PAGE_SIZE);

	assert.equal(calls.length, 1);
	assert.equal(manager.pageSize, MEASURED_PAGE_SIZE);
});

// Measured in the browser after the two requests became one: the request went
// out, 52,945,665 bytes came back, and the manager still showed the 21 seeded
// works. Dropping the duplicate after taking a request number had marked the
// real request as superseded, so its answer was discarded on arrival. One
// request is only worth having if the works in it are the ones on screen.
test('the works that arrive are the works that are shown', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE, 'page'), TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerived(manager);

	manager.openWith(works(STRIP_SIZE), TOTAL, 6);
	refreshDerived(manager);
	manager.setPageSize(MEASURED_PAGE_SIZE);
	await new Promise((resolve) => setTimeout(resolve, 0));

	assert.equal(calls.length, 1);
	assert.equal(manager.activeItems.length, MANAGER_PAGE_SIZE);
	assert.equal(manager.activeItems[0].id, 'page-0');
});

test('measuring itself larger than what is on its way does ask again', () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerived(manager);
	manager.openWith(works(STRIP_SIZE), TOTAL, 6);
	refreshDerived(manager);
	assert.equal(calls.length, 1);

	manager.setPageSize(MANAGER_PAGE_SIZE + 20);

	assert.equal(calls.length, 2);
	assert.equal(new URL(calls[1], 'http://x').searchParams.get('limit'), String(MANAGER_PAGE_SIZE + 20));
});

// The page re-runs its search effect every time the manager opens, dispatching
// the query the manager already has. On a reopen there is nothing in flight to
// ride on, so without this the second press cost a whole page of history for
// works already on screen.
test('reopening does not re-search for the page already in hand', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.pageSize = MANAGER_PAGE_SIZE;
	await manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE });
	refreshDerived(manager);
	assert.equal(calls.length, 1);

	manager.openWith(works(STRIP_SIZE), TOTAL, 6);
	manager.searchChanged('');

	assert.equal(calls.length, 1);
});

test('a real search still asks, even with a page in hand', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.pageSize = MANAGER_PAGE_SIZE;
	await manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE });
	refreshDerived(manager);

	manager.searchChanged('mountain');

	assert.equal(calls.length, 2);
	assert.equal(new URL(calls[1], 'http://x').searchParams.get('q'), 'mountain');
});

test('a different page is not swallowed as a duplicate', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.pageSize = MANAGER_PAGE_SIZE;
	await Promise.all([
		manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE }),
		manager.fetch({ view: 'active', page: 1, pageSize: MANAGER_PAGE_SIZE }),
		manager.fetch({ view: 'trash', page: 0, pageSize: MANAGER_PAGE_SIZE })
	]);
	assert.equal(calls.length, 3);
});

// ── T-6 ─────────────────────────────────────────────────────────────────────
test('opening it again with the page already in hand fetches nothing', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.pageSize = MANAGER_PAGE_SIZE;
	await manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE });
	refreshDerived(manager);
	assert.equal(calls.length, 1);
	assert.equal(
		manager.preloadMatches('active', 0, MANAGER_PAGE_SIZE, '', false, false, TOTAL),
		true
	);

	manager.openWith(works(STRIP_SIZE), TOTAL, 6);

	assert.equal(calls.length, 1);
});
