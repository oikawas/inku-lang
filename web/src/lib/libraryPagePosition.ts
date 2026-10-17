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
