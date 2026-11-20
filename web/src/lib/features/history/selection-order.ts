/** One-based position in the author's selection, or zero when unselected. */
export function selectionOrder(ids: readonly string[], id: string | null | undefined): number {
	return id ? ids.indexOf(id) + 1 : 0;
}
