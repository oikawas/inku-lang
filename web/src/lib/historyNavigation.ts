/**
 * What the history navigation buttons decide, out where a test can drive it.
 *
 * Seventeen buttons move through the same listing, and before this module each
 * of them worked it out again: the canvas from a cursor, the strip from a page
 * number, the modal from its own. They disagreed about which way is newer, about
 * what "latest" counts in, and about where a press lands when it crosses a page.
 *
 * All of it is pure and lives here; the route-instance browsing owner applies
 * the answers. This is for the same
 * reason `historyListLimit.ts` and `historyRefreshDecision.ts` do: `test:unit`
 * is node --test with no DOM, so a decision left inside a component is a
 * decision no gate can reach.
 *
 * One convention runs through the whole file. A *global index* counts works from
 * the newest, across the entire listing: 0 is the newest work, `total - 1` the
 * oldest. `offset` is the global index of the first work the strip is holding,
 * and `cursor` is a position inside that handful. Every rule below is stated in
 * global indexes, because that is the only counting the three boxes share.
 */

/** Where the strip is standing, as the six quantities every button reads. */
export type HistoryNavState = {
	/** Index into the strip's items. -1 when nothing is selected. */
	cursor: number;
	/** Global index of the strip's first item. */
	offset: number;
	total: number;
	windowSize: number;
	/**
	 * A listing request is on its way. Pressing again would double-fetch: the
	 * offset has not moved yet, so the second press asks for the same page and
	 * both presses land on the same work.
	 */
	busy?: boolean;
	/** A demo is running, so nothing may move. */
	locked?: boolean;
};

export type HistoryNavButton = 'latest' | 'newer' | 'older';

/**
 * The pager's buttons. It has one the per-work navigation does not: 'oldest'
 * jumps to the far end of the listing, which only makes sense a page at a time.
 * Kept as a widening of HistoryNavButton rather than as a fourth member of it,
 * so `historyNavDisabled` still answers for exactly the three buttons the canvas
 * and the strip share.
 */
export type HistoryPageButton = HistoryNavButton | 'oldest';

/**
 * Which item is selected, counted from the newest. -1 when nothing is.
 *
 * Nothing selected is a real state the user reaches without asking for it --
 * switching the Stage 1 model, choosing another color catalog, detaching a
 * lineage and three more routes all clear the selection while leaving the work
 * on the canvas. It is read below as "one before the newest", which is what
 * makes all three buttons reachable from it.
 */
export function historyNavPosition(state: HistoryNavState): number {
	return state.cursor < 0 ? -1 : state.offset + state.cursor;
}

export function historyNavDisabled(state: HistoryNavState): Record<HistoryNavButton, boolean> {
	// Whatever else is true, a listing on its way or a demo in progress stops all
	// three. Checked first so no other rule can hand back an enabled button.
	if (state.busy || state.locked) return { latest: true, newer: true, older: true };
	const position = historyNavPosition(state);
	const empty = state.total === 0;
	return {
		latest: empty || position === 0,
		newer: empty || position === 0,
		// From -1 there is somewhere older to go -- the newest work itself.
		older: empty || position === state.total - 1
	};
}

/**
 * Where a press lands. `select` is an index into the page named by `offset`;
 * 'oldest-on-page' is the last item of it, which is only known once it arrives.
 */
export type HistoryNavTarget = { offset: number; select: number | 'oldest-on-page' };

/**
 * Which page holds a global index, and where in it.
 *
 * The page in hand is preferred over the page arithmetic would name. They are
 * normally the same, but a listing fetched around one particular work comes back
 * at whatever offset the server centred on, which need not sit on the grid; from
 * there, recomputing would refetch a page already held and select the wrong item
 * in it.
 */
function seatOf(state: HistoryNavState, index: number): HistoryNavTarget {
	const size = Math.max(1, state.windowSize);
	if (index >= state.offset && index < state.offset + size) {
		return { offset: state.offset, select: index - state.offset };
	}
	const offset = Math.floor(index / size) * size;
	return { offset, select: index - offset };
}

export function historyNavTarget(state: HistoryNavState, button: HistoryNavButton): HistoryNavTarget | null {
	if (historyNavDisabled(state)[button]) return null;
	const position = historyNavPosition(state);
	if (button === 'latest') return { offset: 0, select: 0 };
	// From -1 both directions mean the same thing, and both say so by arriving at
	// the newest work: there is no selection to step away from.
	const index = button === 'newer' ? Math.max(0, position - 1) : position + 1;
	return seatOf(state, index);
}

/** The same three buttons, moving a page at a time (the strip's pager). */
export function historyPageTarget(state: HistoryNavState, button: HistoryPageButton): HistoryNavTarget | null {
	if (state.busy || state.locked || state.total === 0) return null;
	const size = Math.max(1, state.windowSize);
	const page = Math.floor(Math.max(0, state.offset) / size);
	const totalPages = Math.max(1, Math.ceil(state.total / size));
	if (button === 'oldest') {
		// The mirror of 'latest', and counted the same way -- in works, not in
		// pages -- so the two ends of the listing are disabled by the same rule
		// the per-work buttons use. It lands on the oldest work rather than on
		// the newest of the last page, which is what its name says.
		if (historyNavDisabled(state).older) return null;
		return { offset: Math.floor(Math.max(0, state.total - 1) / size) * size, select: 'oldest-on-page' };
	}
	if (button === 'latest') {
		// Counted in works, not in pages, so this button and the canvas's "latest"
		// are never enabled and disabled at the same moment on the same screen.
		if (historyNavDisabled(state).latest) return null;
		return { offset: 0, select: 0 };
	}
	if (button === 'newer') {
		if (page <= 0) return null;
		// The oldest work on the newer page, so stepping a page reads continuously
		// with stepping a work: one press back from the newest work on this page
		// is the oldest work on that one. Landing on its newest instead skipped
		// everything between.
		return { offset: (page - 1) * size, select: 'oldest-on-page' };
	}
	if (page >= totalPages - 1) return null;
	return { offset: (page + 1) * size, select: 0 };
}

/**
 * Re-seat an offset on the grid a new window width defines.
 *
 * The strip holds as many thumbnails as fit, so the window width decides the
 * page size; `offset` was chosen under the old one and stays put, while the page
 * number is recomputed under the new one. From then on a press steps by the new
 * size from a place on the old grid, which shows works twice going older and
 * steps over them going newer -- ten works between two screens, in the measured
 * example, appearing on neither.
 *
 * Rounding down rather than up: rounding up carries some of what is on screen
 * past the top of the next page, so a work goes by unseen. Rounding down shows
 * at worst a few works a second time, and drops none.
 */
export function alignHistoryOffset(offset: number, windowSize: number, total: number): number {
	const size = Math.max(1, windowSize);
	const onGrid = Math.floor(Math.max(0, offset) / size) * size;
	const lastPage = Math.floor(Math.max(0, total - 1) / size) * size;
	return Math.min(onGrid, lastPage);
}

/**
 * Where a work sits in the strip right now, or -1 if it has moved off it.
 *
 * The strip used to hand back the position that was clicked, which is only the
 * work that was clicked for as long as the listing stands still. It does not:
 * every twelve seconds a work saved in another window is taken in at the front
 * and everything shifts by one, and changing the window width reseats the whole
 * page. Both happen while the user is looking at the thumbnails and neither is
 * something they did.
 */
export function resolveStripSelection(items: { id?: string }[], item: { id?: string }): number {
	if (!item?.id) return -1;
	return items.findIndex((candidate) => candidate.id === item.id);
}
