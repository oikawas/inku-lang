import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { LineageNode } from './types.ts';
import type { FetchHistoryResult } from './browsing-state.svelte.ts';

type FetchOffset = (
	offset: number,
	options?: { anchorId?: string; preserveSelection?: boolean; signal?: AbortSignal }
) => Promise<FetchHistoryResult>;

export type FocusSavedLineageDependencies = {
	fetchOffset: FetchOffset;
	filtered: () => boolean;
	clearFilters: () => void;
	items: () => HistoryItem[];
	displayCurrentItem: (item: HistoryItem) => void;
	loadLineage: (nodeId: string) => Promise<void>;
	missingIdentityError: () => Error;
	missingWorkError: () => Error;
};

/** Retry a missing anchor once after removing the filters that can hide it. */
export async function fetchAnchorWithFilterReset(
 historyId: string,
 deps: { fetchOffset: FetchOffset; filtered: () => boolean; clearFilters: () => void; isCurrent?: () => boolean; signal?: AbortSignal },
): Promise<FetchHistoryResult> {
 let found = await deps.fetchOffset(0, { anchorId: historyId, ...(deps.signal ? { signal: deps.signal } : {}) });
 if (deps.isCurrent && !deps.isCurrent()) return 'superseded';
 if (found === 'missing' && deps.filtered()) {
  deps.clearFilters();
  found = await deps.fetchOffset(0, { anchorId: historyId, ...(deps.signal ? { signal: deps.signal } : {}) });
 }
 return deps.isCurrent && !deps.isCurrent() ? 'superseded' : found;
}

/** Focus the saved child in browsing, on the canvas, and in lineage order. */
export async function focusSavedLineageChild(
	historyId: string | null | undefined,
	nodeId: string | null | undefined,
	deps: FocusSavedLineageDependencies
): Promise<void> {
	if (!historyId || !nodeId) throw deps.missingIdentityError();
	const found = await fetchAnchorWithFilterReset(historyId, deps);
	if (found === 'superseded') return;
	if (found !== 'found') throw deps.missingWorkError();
	const saved = deps.items().find((item) => item.id === historyId);
	if (!saved) throw deps.missingWorkError();
	deps.displayCurrentItem(saved);
	await deps.loadLineage(nodeId);
}

export type SaveLineageNoteDependencies = {
	apiFetch: ApiFetch;
	contextVersion: () => number;
	applyStarState: (item: HistoryItem) => void;
	loadLineage: (nodeId: string) => Promise<void>;
};

/** Save the lineage note through the canonical star projection. */
export async function saveLineageNote(
	node: LineageNode,
	note: string,
	deps: SaveLineageNoteDependencies
): Promise<void> {
	if (!node.history?.id) return;
	const contextVersion = deps.contextVersion();
	const response = await deps.apiFetch(`/api/history/${encodeURIComponent(node.history.id)}/star`, {
		method: 'PATCH',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ starred: !!node.history.starred, note: note.trim().slice(0, 240) })
	});
	if (!response.ok) throw new Error(`HTTP ${response.status}`);
	const updated = await response.json() as HistoryItem;
	if (contextVersion !== deps.contextVersion()) return;
	deps.applyStarState(updated);
	await deps.loadLineage(node.id);
}
