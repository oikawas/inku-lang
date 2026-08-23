import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { LineageNode } from './types.ts';

type FetchOffset = (
	offset: number,
	options?: { anchorId?: string; preserveSelection?: boolean }
) => Promise<boolean>;

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

/** Focus the saved child in browsing, on the canvas, and in lineage order. */
export async function focusSavedLineageChild(
	historyId: string | null | undefined,
	nodeId: string | null | undefined,
	deps: FocusSavedLineageDependencies
): Promise<void> {
	if (!historyId || !nodeId) throw deps.missingIdentityError();
	let found = await deps.fetchOffset(0, { anchorId: historyId });
	if (!found && deps.filtered()) {
		deps.clearFilters();
		found = await deps.fetchOffset(0, { anchorId: historyId });
	}
	const saved = deps.items().find((item) => item.id === historyId);
	if (!saved) throw deps.missingWorkError();
	deps.displayCurrentItem(saved);
	await deps.loadLineage(nodeId);
}

export type PromoteLineageDependencies = {
	apiFetch: ApiFetch;
	contextVersion: () => number;
	currentItem: () => HistoryItem | null;
	setCurrentItem: (item: HistoryItem) => void;
	activeHistoryId: () => string | null;
	currentOffset: () => number;
	syncToItem: (item: HistoryItem) => Promise<void>;
	fetchOffset: FetchOffset;
	loadLineage: (nodeId: string) => Promise<void>;
};

/** Promote one lineage node without applying a reply to a newer canvas target. */
export async function promoteLineageNode(
	node: Pick<LineageNode, 'id'>,
	deps: PromoteLineageDependencies
): Promise<void> {
	const contextVersion = deps.contextVersion();
	const response = await deps.apiFetch(`/api/lineage/${encodeURIComponent(node.id)}/promote`, {
		method: 'POST'
	});
	if (!response.ok) return;
	const promoted = await response.json() as HistoryItem;
	if (contextVersion !== deps.contextVersion()) return;
	if (deps.currentItem()?.id === promoted.id) {
		deps.setCurrentItem(promoted);
		await Promise.all([deps.loadLineage(node.id), deps.syncToItem(promoted)]);
		return;
	}
	const activeId = deps.activeHistoryId();
	await Promise.all([
		deps.loadLineage(node.id),
		activeId
			? deps.fetchOffset(0, { anchorId: activeId })
			: deps.fetchOffset(deps.currentOffset(), { preserveSelection: true })
	]);
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
