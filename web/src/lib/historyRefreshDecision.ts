/**
 * The two decisions the twelve-second refresh makes, out where a test can drive
 * them.
 *
 * The refresh exists so a work saved in another window turns up in the strip.
 * It used to answer that by fetching the whole listing every round, which is
 * 23.5 MB with the drawings and 163 KB without them, and in nearly every round
 * it rebuilt no part of the page because nothing had changed. So the round now
 * asks a cheap question first, and only fetches when the answer moves.
 *
 * Both functions are pure: `+page.svelte` holds the live values and calls in.
 * Keeping them here is not tidiness -- `test:unit` is node --test with no DOM,
 * so a decision left inside the component is a decision no gate can reach.
 */

/** What the server says the listing looks like now. */
export type HistoryState = {
	total: number;
	newest_at: number | null;
	newest_id: string | null;
};

/** What the strip is currently showing, as the same three quantities. */
export type HistoryStripHead = {
	total: number;
	newestAt: number | null;
	newestId: string | null;
};

export type HistoryRefreshConditions = {
	signedIn: boolean;
	managerOpen: boolean;
	starredOnly: boolean;
	offset: number;
	loading: boolean;
	visible: boolean;
	inFlight: boolean;
	now: number;
	lastRefreshAt: number;
	minGapMs: number;
};

/**
 * Which guard stops this round, or null to go ahead.
 *
 * It names the guard rather than returning a bare boolean so a failure says
 * which one fired. Every one of these was already in place and every one of
 * them earns its keep: the manager and the starred view and any page but the
 * first are all showing something the strip refresh would overwrite, a hidden
 * tab is not showing anything at all, and a round still in flight would race
 * the one before it.
 *
 * The floor is checked for every caller, including the ones that arrive from
 * `visibilitychange` and `focus`. Those two both fire on a single alt-tab, and
 * they used to skip the floor outright -- measured on 2026-08-11, two rounds
 * 2.5 seconds apart with a five second floor in force. Coming back to the tab
 * still refreshes; what it no longer does is refresh regardless of when the
 * last one was.
 */
export function historyRefreshBlockedBy(c: HistoryRefreshConditions): string | null {
	if (!c.signedIn) return 'signed-out';
	if (c.managerOpen) return 'manager-open';
	if (c.starredOnly) return 'starred-only';
	if (c.offset !== 0) return 'not-the-first-page';
	if (c.loading) return 'drawing';
	if (!c.visible) return 'tab-hidden';
	if (c.now - c.lastRefreshAt < c.minGapMs) return 'too-soon';
	if (c.inFlight) return 'already-asking';
	return null;
}

/**
 * Does the strip already show what the server just described?
 *
 * Compared against the strip itself rather than against the answer remembered
 * from last round. The strip is the thing the refresh keeps current, so asking
 * it directly needs no seeding when the page mounts -- a listing has been
 * loaded by then -- and a fetch that failed leaves the strip stale, so the next
 * round disagrees again and retries. A remembered answer would have filed the
 * change as handled and gone quiet.
 *
 * `newestId` is compared as well as `newestAt` because two works saved inside
 * one millisecond share an `at`; on `at` alone the second one is invisible.
 */
export function historyStripIsCurrent(state: HistoryState, strip: HistoryStripHead): boolean {
	return state.total === strip.total
		&& state.newest_id === strip.newestId
		&& state.newest_at === strip.newestAt;
}
