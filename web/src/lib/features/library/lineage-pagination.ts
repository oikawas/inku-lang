export const LINEAGE_CHUNK_SIZE = 200;

export function visibleLineageCount(count: number | undefined): number {
	return count ?? LINEAGE_CHUNK_SIZE;
}
