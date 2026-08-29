import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type {
	FetchHistoryOptions,
	HistoryForRevisionProjection,
	HistoryForShareProjection,
	HistoryStarProjection
} from './browsing-state.svelte.ts';

export type HistoryBulkMutationPath =
	| '/api/history/trash'
	| '/api/history/restore'
	| '/api/history/permanent-delete';

type HistoryMutationManager = {
	starredOnly: boolean;
	forRevisionOnly: boolean;
	forShareOnly: boolean;
	selectedIds: string[];
	fetch: () => Promise<unknown>;
};

export type HistoryMutationBrowsing = {
	items: HistoryItem[];
	offset: number;
	cursor: number;
	windowSize: number;
	starredOnly: boolean;
	forRevisionOnly: boolean;
	forShareOnly: boolean;
	manager: HistoryMutationManager;
	applyStarState: (item: HistoryStarProjection) => void;
	applyForRevisionState: (item: HistoryForRevisionProjection) => void;
	applyForShareState: (item: HistoryForShareProjection) => void;
	clearStarredFilter: () => void;
	clearForRevisionFilter: () => void;
	clearForShareFilter: () => void;
	clearSelection: () => void;
	syncToItem: (item: Pick<HistoryItem, 'id' | 'trashed' | 'history_visibility'>) => Promise<void>;
	fetchOffset: (offset: number, options?: FetchHistoryOptions) => Promise<boolean>;
	fetchTrashPage: () => Promise<void>;
};

export type HistoryMutationDependencies = {
	apiFetch: ApiFetch;
	signedIn: () => boolean;
	browsing: HistoryMutationBrowsing;
	currentItem: () => HistoryItem | null;
	setCurrentItem: (item: HistoryItem | null) => void;
	applyCurrentResultStarState: (item: HistoryStarProjection) => void;
	applyLineageStarState: (item: HistoryStarProjection) => void;
	applyLineageForRevisionState: (item: HistoryForRevisionProjection) => void;
	applyLineageForShareState: (item: HistoryForShareProjection) => void;
	focusedLineageNodeId: () => string | null;
	reloadLineage: (nodeId: string) => Promise<void>;
	displayCurrentItem: (item: HistoryItem) => void;
	clearCurrentWork: () => void;
	warn?: (message: string, error: unknown) => void;
};

/**
 * Coordinate history mutations across the existing browsing and lineage owners.
 *
 * This route-instance object owns requests and ordering, but no duplicate state.
 * The page supplies only the current canvas projection because Stage 6 still
 * owns the fields needed to adopt a work as the current drawing.
 */
export class HistoryMutations {
	private readonly deps: HistoryMutationDependencies;

	constructor(deps: HistoryMutationDependencies) {
		this.deps = deps;
	}

	toggleStar = async (
		item: HistoryStarProjection | null | undefined,
		event?: Event
	): Promise<void> => {
		event?.stopPropagation();
		if (!item?.id) return;
		const nextStarred = !item.starred;
		this.applyStarState({ ...item, starred: nextStarred });
		try {
			const response = await this.deps.apiFetch(`/api/history/${item.id}/star`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ starred: nextStarred })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const updated = await response.json() as HistoryItem;
			this.applyStarState(updated);
			const refreshes: Promise<unknown>[] = [];
			if (this.deps.browsing.starredOnly) {
				if (!updated.starred) this.deps.browsing.clearStarredFilter();
				refreshes.push(this.deps.browsing.fetchOffset(0, { anchorId: updated.id }));
			}
			if (this.deps.browsing.manager.starredOnly) {
				refreshes.push(this.deps.browsing.manager.fetch());
			}
			if (refreshes.length > 0) await Promise.all(refreshes);
		} catch (error) {
			this.applyStarState(item);
			this.warn('failed to update history star', error);
		}
	};

	toggleForRevision = async (
		item: HistoryForRevisionProjection | null | undefined,
		event?: Event
	): Promise<void> => {
		event?.stopPropagation();
		if (!item?.id) return;
		const nextForRevision = !item.for_revision;
		this.projectForRevision({ ...item, for_revision: nextForRevision });
		try {
			const response = await this.deps.apiFetch(`/api/history/${item.id}/for-revision`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ for_revision: nextForRevision })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const updated = await response.json() as HistoryItem;
			this.projectForRevision(updated);
			const refreshes: Promise<unknown>[] = [];
			if (this.deps.browsing.forRevisionOnly) {
				// Removing a work from the active filter must not leave the strip
				// pointing at an item it no longer contains.
				if (!updated.for_revision) this.deps.browsing.clearForRevisionFilter();
				refreshes.push(this.deps.browsing.fetchOffset(0, { anchorId: updated.id }));
			}
			if (this.deps.browsing.manager.forRevisionOnly) {
				refreshes.push(this.deps.browsing.manager.fetch());
			}
			if (refreshes.length > 0) await Promise.all(refreshes);
		} catch (error) {
			this.projectForRevision(item);
			this.warn('failed to update the revision mark', error);
		}
	};

	toggleForShare = async (
		item: HistoryForShareProjection | null | undefined,
		event?: Event
	): Promise<void> => {
		event?.stopPropagation();
		if (!item?.id) return;
		const nextForShare = !item.for_share;
		// The server alone resolves a bare share bit to a destination. Optimism
		// changes only the bit and keeps the last known destination until reply.
		this.projectForShare({ ...item, for_share: nextForShare });
		try {
			const response = await this.deps.apiFetch(`/api/history/${item.id}/for-share`, {
				method: 'PATCH',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ for_share: nextForShare })
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const updated = await response.json() as HistoryItem;
			this.projectForShare(updated);
			const refreshes: Promise<unknown>[] = [];
			if (this.deps.browsing.forShareOnly) {
				if (!updated.for_share) this.deps.browsing.clearForShareFilter();
				refreshes.push(this.deps.browsing.fetchOffset(0, { anchorId: updated.id }));
			}
			if (this.deps.browsing.manager.forShareOnly) {
				refreshes.push(this.deps.browsing.manager.fetch());
			}
			if (refreshes.length > 0) await Promise.all(refreshes);
		} catch (error) {
			this.projectForShare(item);
			this.warn('failed to update the share mark', error);
		}
	};

	postIds = async (path: HistoryBulkMutationPath, ids: string[]): Promise<void> => {
		if (!this.deps.signedIn()) return;
		await this.deps.apiFetch(path, {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ids })
		});

		const current = this.deps.currentItem();
		// Capture this before changing the flag: it decides whether the refreshed
		// strip must also reseat the canvas on a work that still belongs to it.
		const displayedLeavesTheListing = !!current?.id
			&& ids.includes(current.id)
			&& (path === '/api/history/trash' || path === '/api/history/permanent-delete');
		if (current?.id && ids.includes(current.id)) {
			if (path === '/api/history/trash') {
				this.deps.setCurrentItem({ ...current, trashed: true });
				this.deps.browsing.clearSelection();
			} else if (path === '/api/history/restore') {
				const restored = { ...current, trashed: false };
				this.deps.setCurrentItem(restored);
				void this.deps.browsing.syncToItem(restored);
			} else {
				this.deps.setCurrentItem(null);
				this.deps.browsing.clearSelection();
			}
		}

		this.deps.browsing.manager.selectedIds = [];
		await Promise.all([
			this.deps.browsing.fetchOffset(this.deps.browsing.offset),
			this.deps.browsing.fetchTrashPage(),
			this.deps.browsing.manager.fetch()
		]);
		const focusedNodeId = this.deps.focusedLineageNodeId();
		if (focusedNodeId) await this.deps.reloadLineage(focusedNodeId);
		if (this.deps.browsing.items.length === 0 && this.deps.browsing.offset > 0) {
			await this.deps.browsing.fetchOffset(Math.max(
				0,
				this.deps.browsing.offset - this.deps.browsing.windowSize
			));
		}

		if (!displayedLeavesTheListing) return;
		const next = this.deps.browsing.items[this.deps.browsing.cursor];
		if (next) this.deps.displayCurrentItem(next);
		else this.deps.clearCurrentWork();
	};

	applyStarState(item: HistoryStarProjection): void {
		if (!item.id) return;
		const hasNote = Object.prototype.hasOwnProperty.call(item, 'note');
		this.deps.browsing.applyStarState(item);
		const current = this.deps.currentItem();
		if (current?.id === item.id) {
			this.deps.setCurrentItem({
				...current,
				starred: item.starred,
				note: hasNote ? item.note : current.note
			});
		}
		this.deps.applyCurrentResultStarState(item);
		this.deps.applyLineageStarState(item);
	}

	private projectForRevision(item: HistoryForRevisionProjection): void {
		if (!item.id) return;
		this.deps.browsing.applyForRevisionState(item);
		const current = this.deps.currentItem();
		if (current?.id === item.id) {
			this.deps.setCurrentItem({ ...current, for_revision: item.for_revision });
		}
		this.deps.applyLineageForRevisionState(item);
	}

	private projectForShare(item: HistoryForShareProjection): void {
		if (!item.id) return;
		const next = { for_share: item.for_share, share_group_id: item.share_group_id };
		this.deps.browsing.applyForShareState(item);
		const current = this.deps.currentItem();
		if (current?.id === item.id) this.deps.setCurrentItem({ ...current, ...next });
		this.deps.applyLineageForShareState(item);
	}

	private warn(message: string, error: unknown): void {
		if (this.deps.warn) this.deps.warn(message, error);
		else console.warn(message, error);
	}
}
