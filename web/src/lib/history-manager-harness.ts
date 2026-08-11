// Test-only harness for driving the real HistoryManagerState under node --test.
//
// Not a test file: `test:unit` globs src/**/*.test.ts, which this name does not
// match. It lives here so the rune shim and, more importantly, the hand-written
// stand-in for $derived exist once. Two copies of refreshDerived would be two
// chances for the copy to fall behind the class it mirrors, and a gate that
// mirrors the wrong expression stays green while the product moves.
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

export const { HistoryManagerState } = await import('./historyManagerState.svelte.ts');

export type Manager = InstanceType<typeof HistoryManagerState>;

/** Works enough for the manager to count; nothing here reads their contents. */
export function works(count: number, prefix = 'w'): HistoryItem[] {
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
export function makeManager(pageItems: HistoryItem[], total: number) {
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
 *
 * `items` must be sliced exactly the way the class slices it. It is one page's
 * worth, not everything in hand: the two differ whenever the page guessed a
 * larger size than the modal went on to measure, which is the ordinary case.
 *
 * All five derived fields are caught up, not just the two the code reads most.
 * `totalPages` is frozen at 1 on a fresh manager, and setPage() clamps against
 * it, so leaving it behind turns every page change into a silent no-op -- the
 * gate then reads the first page twice and reports it as an overlap.
 */
export function refreshDerived(manager: Manager) {
	const trash = manager.view === 'trash';
	const held = trash ? manager.trashItems : manager.activeItems;
	manager.total = trash ? manager.trashTotal : manager.activeTotal;
	manager.totalPages = Math.max(1, Math.ceil(manager.total / manager.pageSize));
	manager.offset = manager.page * manager.pageSize;
	manager.items = held.slice(0, manager.pageSize);
	manager.shownTo = Math.min(manager.offset + manager.items.length, manager.total);
}

export const STRIP_SIZE = 21;
/** What the page guesses a manager page holds, before the modal exists. */
export const MANAGER_PAGE_SIZE = 65;
/** What the modal reports once it is on screen and has measured its grid. */
export const MEASURED_PAGE_SIZE = 52;
export const TOTAL = 2917;
