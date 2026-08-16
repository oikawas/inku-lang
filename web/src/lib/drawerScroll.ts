// Where the provenance drawer was left when it was closed.
//
// The drawer is never removed from the page -- it is clipped away -- so one
// might expect the browser to keep the position by itself. It does not keep it
// reliably: the drawer's contents are rebuilt whenever the work on screen
// changes, and a work with fewer rows is a shorter pane, which clamps the
// scroll it was holding. Reopening then starts at the top of a list the reader
// had already scrolled past.
//
// So the position is remembered here instead, per tab: the drawer also
// remembers which tab was open, and restoring one without the other would put
// the reader at a depth that belongs to a different list.

export type DrawerTab = 'details' | 'prompts' | 'score';

export type DrawerScrollMemory = Record<DrawerTab, number>;

export const emptyDrawerScrollMemory = (): DrawerScrollMemory => ({
	details: 0,
	prompts: 0,
	score: 0
});

/**
 * The memory after closing on `tab` at `scrollTop`.
 *
 * A negative offset (rubber-band scrolling on a trackpad) is not a position to
 * come back to, so it is kept as the top.
 */
export function rememberDrawerScroll(
	memory: DrawerScrollMemory,
	tab: DrawerTab,
	scrollTop: number
): DrawerScrollMemory {
	return { ...memory, [tab]: Number.isFinite(scrollTop) && scrollTop > 0 ? scrollTop : 0 };
}

/** Where to put the reader when the drawer opens on `tab`. */
export function drawerScrollToRestore(memory: DrawerScrollMemory, tab: DrawerTab): number {
	return memory[tab] ?? 0;
}
