/**
 * Where a Library page sits among all of them, counted from the newest.
 *
 * The Library can start at the selected work rather than at the newest, and
 * pages on from that start (`page`). Counting from the start said 1 at the
 * selected work and added a page to the total for each step towards the newest.
 * The pages in front of the start are the presses of "Newer" it takes to reach
 * the newest, so they come first in the number and in the total.
 */
export function libraryPagePosition(startOffset: number, page: number, pageSize: number, total: number): { current: number; total: number } {
	const size = Math.max(1, pageSize);
	const before = Math.ceil(Math.max(0, startOffset) / size);
	const after = Math.max(1, Math.ceil((total - startOffset) / size));
	return { current: before + page + 1, total: before + after };
}

/**
 * The page to ask for when the reader types page `n` of the numbers above.
 *
 * Counted from the start, as `setPage` takes it: a negative page moves the
 * start towards the newest, to where pressing "Newer" that many times would
 * have put it. Out-of-range numbers land on the first or the last page.
 */
export function libraryRelativePage(n: number, startOffset: number, pageSize: number, total: number): number {
	const size = Math.max(1, pageSize);
	const before = Math.ceil(Math.max(0, startOffset) / size);
	const position = libraryPagePosition(startOffset, 0, size, total);
	const target = Math.max(1, Math.min(Math.trunc(n), position.total));
	return target - 1 - before;
}
