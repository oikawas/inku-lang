export const LINEAGE_CHUNK_SIZE = 200;

export function visibleLineageCount(count: number | undefined): number {
	return count ?? LINEAGE_CHUNK_SIZE;
}

export function lineageArrowTarget(index: number, total: number, shown: number, key: string): { index: number; shown: number } | null {
	if (!['ArrowLeft', 'ArrowRight', 'ArrowUp', 'ArrowDown'].includes(key)) return null;
	const next = index + (key === 'ArrowLeft' || key === 'ArrowUp' ? -1 : 1);
	if (index < 0 || next < 0 || next >= total) return null;
	return { index: next, shown: next >= shown ? shown + LINEAGE_CHUNK_SIZE : shown };
}
