import type { ApiFetch } from '../../transport/api-fetch.ts';
import {
	HistoryManagerState,
	type HistoryItem
} from '../../historyManagerState.svelte.ts';
import { historyListLimit } from '../../historyListLimit.ts';
import {
	historyRefreshBlockedBy,
	historyStripIsCurrent,
	type HistoryState
} from '../../historyRefreshDecision.ts';
import {
	alignHistoryOffset,
	historyNavDisabled,
	historyNavTarget,
	historyPageTarget,
	resolveStripSelection,
	type HistoryNavButton,
	type HistoryNavState,
	type HistoryNavTarget,
	type HistoryPageButton
} from '../../historyNavigation.ts';

export const HISTORY_EXTERNAL_REFRESH_MS = 12_000;
export const HISTORY_EXTERNAL_REFRESH_MIN_GAP_MS = 5_000;

export type HistoryStarProjection = {
	id?: string;
	starred?: boolean;
	note?: string | null;
};

export type HistoryForRevisionProjection = {
	id?: string;
	for_revision?: boolean;
};

export type HistoryForShareProjection = {
	id?: string;
	for_share?: boolean;
	share_group_id?: string | null;
};

export type HistoryBrowsingDependencies = {
	apiFetch: ApiFetch;
	signedIn: () => boolean;
	drawing: () => boolean;
	visible: () => boolean;
	navigationLocked: () => boolean;
	currentHistoryId: () => string | null;
	currentItem: () => HistoryItem | null;
	managerPageSize: () => number;
	onStarredFilterCleared: () => void;
	onOtherFilterCleared: () => void;
	now?: () => number;
};

export type FetchHistoryOptions = {
	preserveSelection?: boolean;
	anchorId?: string;
};

/**
 * Route-instance owner for the history strip and its manager coordination.
 *
 * The strip and modal ask different questions, so they keep different paging
 * state. This owner constructs exactly one existing HistoryManagerState rather
 * than copying its request suppression, cache, or measured page-size rules.
 * The page retains the work on the canvas and calls these named operations.
 */
export class HistoryBrowsingState {
	items = $state<HistoryItem[]>([]);
	total = $state(0);
	offset = $state(0);
	cursor = $state(-1);
	windowSize = $state(1);
	fetchInFlight = $state(0);
	starredOnly = $state(false);
	forRevisionOnly = $state(false);
	forShareOnly = $state(false);
	trashItems = $state<HistoryItem[]>([]);
	trashTotal = $state(0);

	readonly manager: HistoryManagerState;

	private readonly deps: HistoryBrowsingDependencies;
	private fetchRequest = 0;
	private selectionRequest = 0;
	private trashRequest = 0;
	private externalRefreshInFlight = false;
	private lastExternalRefreshAt = 0;
	private lastWindowSize = 0;

	constructor(deps: HistoryBrowsingDependencies) {
		this.deps = deps;
		this.manager = new HistoryManagerState(deps.apiFetch, (items, total) => {
			this.trashItems = items;
			this.trashTotal = total;
		});
	}

	get filtered(): boolean {
		return this.starredOnly || this.forRevisionOnly || this.forShareOnly;
	}

	get page(): number {
		return Math.floor(this.offset / Math.max(1, this.windowSize));
	}

	get totalPages(): number {
		return Math.max(1, Math.ceil(this.total / Math.max(1, this.windowSize)));
	}

	get navState(): HistoryNavState {
		return {
			cursor: this.cursor,
			offset: this.offset,
			total: this.total,
			windowSize: this.windowSize,
			busy: this.fetchInFlight > 0,
			locked: this.deps.navigationLocked()
		};
	}

	get navDisabled(): Record<HistoryNavButton, boolean> {
		return historyNavDisabled(this.navState);
	}

	get pageDisabled(): Record<HistoryPageButton, boolean> {
		return {
			latest: this.navDisabled.latest,
			newer: historyPageTarget(this.navState, 'newer') === null,
			older: historyPageTarget(this.navState, 'older') === null,
			oldest: historyPageTarget(this.navState, 'oldest') === null
		};
	}

	clear(): void {
		this.fetchRequest += 1;
		this.selectionRequest += 1;
		this.trashRequest += 1;
		this.items = [];
		this.total = 0;
		this.offset = 0;
		this.cursor = -1;
		this.fetchInFlight = 0;
		this.starredOnly = false;
		this.forRevisionOnly = false;
		this.forShareOnly = false;
		this.trashItems = [];
		this.trashTotal = 0;
		this.externalRefreshInFlight = false;
		this.lastExternalRefreshAt = 0;
		this.manager.clear();
	}

	clearSelection(): void {
		this.cursor = -1;
	}

	setCursor(index: number): void {
		this.cursor = index >= 0 && index < this.items.length ? index : -1;
	}

	select(index: number): HistoryItem | null {
		if (index < 0 || index >= this.items.length) return null;
		this.cursor = index;
		return this.items[index] ?? null;
	}

	async fetchOffset(offset: number, options: FetchHistoryOptions = {}): Promise<boolean> {
		if (!this.deps.signedIn()) {
			this.items = [];
			this.total = 0;
			this.offset = 0;
			return false;
		}
		const safeOffset = Math.max(0, offset);
		// A request number protects the four strip quantities as one answer.
		// Resize and external-refresh callers intentionally do not always await,
		// so a slower old page must never overwrite the latest question.
		const requestId = ++this.fetchRequest;
		this.fetchInFlight += 1;
		const selectedHistoryId = options.anchorId ?? (options.preserveSelection
			? this.items[this.cursor]?.id ?? this.deps.currentHistoryId()
			: null);
		try {
			const listLimit = historyListLimit({
				anchorId: options.anchorId ?? null,
				offset: safeOffset,
				starredOnly: this.starredOnly,
				windowSize: this.windowSize,
				managerPageSize: this.deps.managerPageSize()
			});
			const params = new URLSearchParams({
				offset: String(safeOffset),
				limit: String(listLimit),
				// The strip draws thumbnails; consumers fetch one full SVG when needed.
				include_svg: 'false'
			});
			if (this.starredOnly) params.set('starred', 'true');
			if (this.forRevisionOnly) params.set('for_revision', 'true');
			if (this.forShareOnly) params.set('for_share', 'true');
			if (options.anchorId) params.set('anchor_id', options.anchorId);
			const response = await this.deps.apiFetch(`/api/history?${params.toString()}`);
			if (requestId !== this.fetchRequest || !response.ok) return false;
			const data = await response.json() as {
				items: HistoryItem[];
				total: number;
				offset?: number;
			};
			const resolvedOffset = Number.isFinite(data.offset) ? Number(data.offset) : safeOffset;
			if (data.items.length === 0 && data.total > 0 && resolvedOffset > 0 && !options.anchorId) {
				const lastOffset = Math.floor((data.total - 1) / this.windowSize) * this.windowSize;
				return await this.fetchOffset(lastOffset);
			}
			const stripItems = resolvedOffset === 0 && !this.filtered
				? data.items.slice(0, this.windowSize)
				: data.items;
			// Keep the identity check adjacent to the state write it protects.
			if (requestId !== this.fetchRequest) return false;
			this.items = stripItems;
			this.total = data.total;
			this.offset = resolvedOffset;
			if (selectedHistoryId) {
				const selectedIndex = stripItems.findIndex((item) => item.id === selectedHistoryId);
				if (selectedIndex >= 0) this.cursor = selectedIndex;
				else if (options.anchorId || options.preserveSelection) this.cursor = -1;
				else if (this.cursor >= stripItems.length) this.cursor = stripItems.length > 0 ? 0 : -1;
			} else {
				if (this.cursor >= stripItems.length) this.cursor = stripItems.length > 0 ? 0 : -1;
				if (this.cursor < 0 && stripItems.length > 0) this.cursor = 0;
			}
			if (!this.manager.open && resolvedOffset === 0 && !this.filtered) {
				// Seed what the strip has, but keep the manager's measured page
				// size separate; opening the modal still fetches its own full page.
				this.manager.seedFromStrip(
					data.items,
					data.total,
					this.trashTotal,
					this.deps.managerPageSize()
				);
			}
			return options.anchorId
				? this.cursor >= 0 && this.items[this.cursor]?.id === options.anchorId
				: true;
		} catch {
			return false;
		} finally {
			this.fetchInFlight = Math.max(0, this.fetchInFlight - 1);
		}
	}

	async syncToItem(item: Pick<HistoryItem, 'id' | 'trashed' | 'history_visibility'>): Promise<void> {
		const requestId = ++this.selectionRequest;
		if (!item.id || item.trashed || item.history_visibility === 'lineage_only') {
			this.cursor = -1;
			return;
		}
		const localIndex = resolveStripSelection(this.items, item);
		if (localIndex >= 0) {
			this.cursor = localIndex;
			return;
		}
		this.cursor = -1;
		let found = await this.fetchOffset(0, { anchorId: item.id });
		if (requestId !== this.selectionRequest) {
			const current = this.deps.currentItem();
			if (current) void this.syncToItem(current);
			return;
		}
		if (!found && this.filtered) {
			// All strip filters come off together because the missing response
			// does not say which independent mark hid the current work.
			const clearedStarred = this.starredOnly;
			this.starredOnly = false;
			this.forRevisionOnly = false;
			this.forShareOnly = false;
			if (clearedStarred) this.deps.onStarredFilterCleared();
			else this.deps.onOtherFilterCleared();
			found = await this.fetchOffset(0, { anchorId: item.id });
		}
		if (requestId !== this.selectionRequest) {
			const current = this.deps.currentItem();
			if (current) void this.syncToItem(current);
			return;
		}
		if (!found) this.cursor = -1;
	}

	async fetchTrashPage(): Promise<void> {
		if (!this.deps.signedIn()) {
			this.trashItems = [];
			this.trashTotal = 0;
			return;
		}
		const requestId = ++this.trashRequest;
		try {
			const response = await this.deps.apiFetch(
				'/api/history?offset=0&limit=100&trashed=true&include_svg=false'
			);
			if (requestId !== this.trashRequest || !response.ok) return;
			const data = await response.json() as { items: HistoryItem[]; total: number };
			if (requestId !== this.trashRequest) return;
			this.trashItems = data.items;
			this.trashTotal = data.total;
		} catch {
			// The trash summary is opportunistic; the manager can fetch it later.
		}
	}

	openManager(): void {
		this.manager.openWith(this.items, this.total, this.trashTotal);
	}

	setStarredOnly(value: boolean): void {
		this.starredOnly = value;
		this.offset = 0;
		this.cursor = -1;
		void this.fetchOffset(0);
	}

	setForRevisionOnly(value: boolean): void {
		this.forRevisionOnly = value;
		this.offset = 0;
		this.cursor = -1;
		void this.fetchOffset(0);
	}

	setForShareOnly(value: boolean): void {
		this.forShareOnly = value;
		this.offset = 0;
		this.cursor = -1;
		void this.fetchOffset(0);
	}

	clearStarredFilter(): void {
		this.starredOnly = false;
	}

	clearForRevisionFilter(): void {
		this.forRevisionOnly = false;
	}

	clearForShareFilter(): void {
		this.forShareOnly = false;
	}

	clearFilters(): void {
		this.starredOnly = false;
		this.forRevisionOnly = false;
		this.forShareOnly = false;
	}

	async move(button: HistoryNavButton): Promise<HistoryItem | null> {
		const target = historyNavTarget(this.navState, button);
		if (!target) return null;
		if (target.offset !== this.offset && !(await this.fetchOffset(target.offset))) return null;
		return this.select(this.indexOf(target));
	}

	async movePage(button: HistoryPageButton): Promise<HistoryItem | null> {
		const target = historyPageTarget(this.navState, button);
		if (!target || !(await this.fetchOffset(target.offset))) return null;
		return this.select(this.indexOf(target));
	}

	async resize(windowSize: number): Promise<void> {
		const nextSize = Math.max(1, Math.floor(windowSize));
		this.windowSize = nextSize;
		if (this.lastWindowSize === 0) {
			this.lastWindowSize = nextSize;
			return;
		}
		if (nextSize === this.lastWindowSize) return;
		this.lastWindowSize = nextSize;
		if (!this.deps.signedIn() || this.total <= 0) return;
		// Seat the strip on the new grid before asking. Keeping an old offset
		// under a new page size duplicates works in one direction and skips them
		// in the other.
		this.offset = alignHistoryOffset(this.offset, nextSize, this.total);
		await this.fetchOffset(this.offset);
	}

	/**
	 * Project a newly saved work without pulling a reader off an older page.
	 *
	 * Page zero is refreshed because it is the live newest window. Elsewhere,
	 * only the unfiltered count advances; the chosen window catches up after the
	 * outer run ends.
	 */
	async refreshAfterServerSave(): Promise<void> {
		if (this.offset !== 0) {
			if (!this.filtered) this.total += 1;
			return;
		}
		const activeHistoryId = this.deps.currentHistoryId();
		await this.fetchOffset(0);
		if (!activeHistoryId) {
			this.cursor = 0;
			return;
		}
		this.cursor = this.items.findIndex((item) => item.id === activeHistoryId);
	}

	/** Catch a paged-away strip up after a run, preserving its selected work. */
	async refreshAfterRun(): Promise<void> {
		if (!this.deps.signedIn() || this.offset === 0) return;
		await this.fetchOffset(this.offset, { preserveSelection: true });
	}

	async refreshExternal(): Promise<void> {
		const now = (this.deps.now ?? Date.now)();
		if (historyRefreshBlockedBy({
			signedIn: this.deps.signedIn(),
			managerOpen: this.manager.open,
			starredOnly: this.starredOnly,
			offset: this.offset,
			loading: this.deps.drawing(),
			visible: this.deps.visible(),
			inFlight: this.externalRefreshInFlight,
			now,
			lastRefreshAt: this.lastExternalRefreshAt,
			minGapMs: HISTORY_EXTERNAL_REFRESH_MIN_GAP_MS
		})) return;
		this.externalRefreshInFlight = true;
		this.lastExternalRefreshAt = now;
		try {
			// Ask the cheap state endpoint before carrying the listing. A failed
			// probe deliberately falls through to the old safe listing fetch.
			const state = await this.fetchHistoryState();
			if (state && historyStripIsCurrent(state, {
				total: this.total,
				newestId: this.items[0]?.id ?? null,
				newestAt: this.items[0]?.at ?? null,
				showsTheNewestFirst: this.offset === 0 && !this.filtered
			})) return;
			const activeHistoryId = this.deps.currentHistoryId()
				?? this.items[this.cursor]?.id
				?? null;
			if (activeHistoryId) await this.fetchOffset(0, { anchorId: activeHistoryId });
			else await this.fetchOffset(0, { preserveSelection: true });
			if (
				this.manager.open &&
				this.manager.view === 'active' &&
				this.manager.page === 0 &&
				!this.manager.search.trim() &&
				!this.manager.starredOnly
			) {
				await this.manager.fetch({
					view: 'active',
					page: 0,
					search: '',
					starredOnly: false,
					silent: true
				});
			}
		} finally {
			this.externalRefreshInFlight = false;
		}
	}

	applyStarState(item: HistoryStarProjection): void {
		if (!item.id) return;
		const hasNote = Object.prototype.hasOwnProperty.call(item, 'note');
		this.items = this.items.map((candidate) => candidate.id === item.id
			? { ...candidate, starred: item.starred, note: hasNote ? item.note : candidate.note }
			: candidate);
		this.trashItems = this.trashItems.map((candidate) => candidate.id === item.id
			? { ...candidate, starred: item.starred, note: hasNote ? item.note : candidate.note }
			: candidate);
		this.manager.applyStarState(item);
	}

	applyForRevisionState(item: HistoryForRevisionProjection): void {
		if (!item.id) return;
		this.items = this.items.map((candidate) => candidate.id === item.id
			? { ...candidate, for_revision: item.for_revision }
			: candidate);
		this.trashItems = this.trashItems.map((candidate) => candidate.id === item.id
			? { ...candidate, for_revision: item.for_revision }
			: candidate);
		this.manager.applyForRevisionState(item);
	}

	applyForShareState(item: HistoryForShareProjection): void {
		if (!item.id) return;
		const next = { for_share: item.for_share, share_group_id: item.share_group_id };
		this.items = this.items.map((candidate) => candidate.id === item.id
			? { ...candidate, ...next }
			: candidate);
		this.trashItems = this.trashItems.map((candidate) => candidate.id === item.id
			? { ...candidate, ...next }
			: candidate);
		this.manager.applyForShareState(item);
	}

	private async fetchHistoryState(): Promise<HistoryState | null> {
		try {
			const response = await this.deps.apiFetch('/api/history/state');
			if (!response.ok) return null;
			const data = await response.json();
			if (!Number.isFinite(data?.total)) return null;
			return {
				total: Number(data.total),
				newest_at: data.newest_at ?? null,
				newest_id: data.newest_id ?? null
			};
		} catch {
			return null;
		}
	}

	private indexOf(target: HistoryNavTarget): number {
		return target.select === 'oldest-on-page' ? this.items.length - 1 : target.select;
	}
}
