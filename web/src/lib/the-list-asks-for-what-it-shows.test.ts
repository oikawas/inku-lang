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
 * Let the frozen `items` catch up with `activeItems`.
 *
 * Needed only because the shim above turns $derived into a plain value taken at
 * construction time. In the browser this happens by itself; here it does not,
 * and preloadMatches reads this.items.length.
 */
function refreshDerivedItems(manager: InstanceType<typeof HistoryManagerState>) {
	manager.items = manager.activeItems;
}

const STRIP_SIZE = 21;
const MANAGER_PAGE_SIZE = 65;
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
test('holding the strip is not claimed to be holding a page', () => {
	const { manager } = makeManager([], TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerivedItems(manager);
	assert.equal(
		manager.preloadMatches('active', 0, manager.pageSize, '', false, false, TOTAL),
		false
	);
});

// ── T-5 ─────────────────────────────────────────────────────────────────────
test('opening the manager without a page in hand fetches one', () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.seedFromStrip(works(STRIP_SIZE), TOTAL, 6, MANAGER_PAGE_SIZE);
	refreshDerivedItems(manager);
	assert.equal(calls.length, 0);

	manager.openWith(works(STRIP_SIZE), TOTAL, 6);

	assert.equal(calls.length, 1);
	const asked = new URL(calls[0], 'http://localhost');
	assert.equal(asked.searchParams.get('offset'), '0');
	assert.equal(asked.searchParams.get('limit'), String(MANAGER_PAGE_SIZE));
	// The seeded works stay on screen while the page is on its way.
	assert.equal(manager.activeItems.length, STRIP_SIZE);
});

// ── T-6 ─────────────────────────────────────────────────────────────────────
test('opening it again with the page already in hand fetches nothing', async () => {
	const { manager, calls } = makeManager(works(MANAGER_PAGE_SIZE), TOTAL);
	manager.pageSize = MANAGER_PAGE_SIZE;
	await manager.fetch({ view: 'active', page: 0, pageSize: MANAGER_PAGE_SIZE });
	refreshDerivedItems(manager);
	assert.equal(calls.length, 1);
	assert.equal(
		manager.preloadMatches('active', 0, MANAGER_PAGE_SIZE, '', false, false, TOTAL),
		true
	);

	manager.openWith(works(STRIP_SIZE), TOTAL, 6);

	assert.equal(calls.length, 1);
});
