/**
 * How many works the history list asks the server for.
 *
 * This used to live inside +page.svelte, where no unit test could reach it, and
 * it got one route wrong: on the very first load it asked for the history
 * manager's page size instead of the strip's, so every visit downloaded a page
 * for a modal nobody had opened -- three times what the strip shows.
 *
 * The decision is now one value: the list asks for what the strip shows, on
 * every route. `managerPageSize` is passed in and deliberately not consulted;
 * it is here so a test can hand the two quantities different numbers and see
 * which one comes back. The manager fetches its own page when it opens.
 */
export type HistoryListLimitInput = {
	/** Set when the request is centred on one work, rather than a page of them. */
	anchorId?: string | null;
	offset: number;
	starredOnly: boolean;
	/** How many thumbnails the strip shows at the current window width. */
	windowSize: number;
	/** How many works one page of the history manager holds. Not asked for here. */
	managerPageSize: number;
};

export function historyListLimit({ windowSize }: HistoryListLimitInput): number {
	return windowSize;
}
