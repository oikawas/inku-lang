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
import type { HistoryItem } from './historyManagerState.svelte.ts';

// Runes are a compile-time transform, so plain node has no $state or $derived.
// The tests read values rather than react to them, so an identity shim is
// enough -- but it has to be installed before the module is evaluated, which is
// why the import below is dynamic.
const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = stateShim;
runeHost.$derived = identity;

const { HistoryManagerState } = await import('./historyManagerState.svelte.ts');

/** Works enough for the manager to count; nothing here reads their contents. */
function works(count: number, prefix = 'w'): HistoryItem[] {
	return Array.from({ length: count }, (_, i) => ({
		id: `${prefix}-${i}`,
		input: '',
		ddl: null,
		score: { instructions: [] },
		svg: '',
		at: 0
	}));
}

/** The manager, plus the list of paths it asked the server for. */
function makeManager(pageItems: HistoryItem[], total: number) {
	const calls: string[] = [];
	const apiFetch = async (path: string) => {
		calls.push(path);
		return {
			ok: true,
			json: async () => ({ items: pageItems, total })
		} as unknown as Response;
	};
	const manager = new HistoryManagerState(apiFetch, () => {});
	return { manager, calls };
}

/**
 * Let the frozen derived values catch up with the state they are derived from.
 *
 * Needed only because the shim above turns $derived into a plain value taken at
 * construction time. In the browser this happens by itself; here it does not,
 * and the code under test reads both -- preloadMatches reads this.items.length,
 * setPageSize reads this.total. Leaving `total` frozen at 0 makes setPageSize
 * think no works are expected, so it asks for nothing and a gate on asking
 * passes without the code ever having decided anything.
 */
function refreshDerived(manager: InstanceType<typeof HistoryManagerState>) {
	manager.items = manager.activeItems;
	manager.total = manager.activeTotal;
}

const STRIP_SIZE = 21;
/** What the page guesses a manager page holds, before the modal exists. */
const MANAGER_PAGE_SIZE = 65;
/** What the modal reports once it is on screen and has measured its grid. */
const MEASURED_PAGE_SIZE = 52;
const TOTAL = 2917;

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
