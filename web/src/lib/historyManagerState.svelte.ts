export const HISTORY_MANAGER_DEFAULT_PAGE_SIZE = 24;

export type HistoryManagerView = 'active' | 'trash';
export type HistoryManagerTab = 'thumbs' | 'list';

export type Score = { instructions: unknown[]; canvas?: string | null };

export type HistoryItem = {
	id?: string;
	input: string;
	ddl: string | null;
	thinking?: string | null;
	score: Score;
	svg: string;
	at: number;
	elapsed_ms?: number;
	stage1_model?: string | null;
	stage2_model?: string | null;
	tokens_in?: number | null;
	tokens_out?: number | null;
	catalog_id?: string | null;
	render_build_number?: string | null;
	render_color_profile?: Record<string, string> | null;
	render_color_catalog_id?: string | null;
	render_color_catalog_name?: string | null;
	render_color_catalog_sub?: string | null;
	render_color_map?: Record<string, string> | null;
	render_hash?: string | null;
	render_hash_short?: string | null;
	trashed?: boolean;
	starred?: boolean;
};

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type TrashPageSync = (items: HistoryItem[], total: number) => void;

type FetchOptions = {
	view?: HistoryManagerView;
	page?: number;
	search?: string;
	starredOnly?: boolean;
	pageSize?: number;
	silent?: boolean;
};

export class HistoryManagerState {
	open = $state(false);
	view = $state<HistoryManagerView>('active');
	tab = $state<HistoryManagerTab>('thumbs');
	page = $state(0);
	pageSize = $state(HISTORY_MANAGER_DEFAULT_PAGE_SIZE);
	loading = $state(false);
	starredOnly = $state(false);
	activeItems = $state<HistoryItem[]>([]);
	activeTotal = $state(0);
	trashItems = $state<HistoryItem[]>([]);
	trashTotal = $state(0);
	search = $state('');
	selectedIds = $state<string[]>([]);
	private requestId = 0;
	private pendingRequests = 0;
	private preloadKey = "";

	items = $derived(this.view === 'trash' ? this.trashItems : this.activeItems);
	total = $derived(this.view === 'trash' ? this.trashTotal : this.activeTotal);
	totalPages = $derived(Math.max(1, Math.ceil(this.total / this.pageSize)));
	offset = $derived(this.page * this.pageSize);
	shownTo = $derived(Math.min(this.offset + this.items.length, this.total));

	constructor(
		private readonly apiFetch: ApiFetch,
		private readonly syncTrashPage: TrashPageSync
	) {}

	clear() {
		this.open = false;
		this.view = 'active';
		this.tab = 'thumbs';
		this.page = 0;
		this.pageSize = HISTORY_MANAGER_DEFAULT_PAGE_SIZE;
		this.loading = false;
		this.starredOnly = false;
		this.activeItems = [];
		this.activeTotal = 0;
		this.trashItems = [];
		this.trashTotal = 0;
		this.search = '';
		this.selectedIds = [];
		this.requestId += 1;
		this.pendingRequests = 0;
		this.preloadKey = "";
	}

	openWith(activeItems: HistoryItem[], activeTotal: number, trashTotal: number) {
		this.open = true;
		this.view = 'active';
		this.tab = 'thumbs';
		this.page = 0;
		this.search = '';
		this.selectedIds = [];
		if (!this.preloadMatches('active', 0, this.pageSize, '', false, activeTotal)) {
			this.activeItems = activeItems;
		}
		this.activeTotal = activeTotal;
		this.trashItems = [];
		this.trashTotal = trashTotal;
	}

	fetch = async (options: FetchOptions = {}): Promise<void> => {
		const requestId = ++this.requestId;
		const view = options.view ?? this.view;
		const page = options.page ?? this.page;
		const search = options.search ?? this.search.trim();
		const starredOnly = options.starredOnly ?? this.starredOnly;
		const pageSize = options.pageSize ?? this.pageSize;
		const silent = options.silent ?? false;
		this.pendingRequests += 1;
		if (!silent) this.loading = true;
		try {
			const trashed = view === 'trash';
			const offset = page * pageSize;
			const params = new URLSearchParams({
				offset: String(offset),
				limit: String(pageSize),
				q: search,
			});
			if (trashed) params.set('trashed', 'true');
			if (starredOnly) params.set('starred', 'true');
			const r = await this.apiFetch(`/api/history?${params.toString()}`);
			if (requestId !== this.requestId) return;
			if (!r.ok) return;
			const data = await r.json() as { items: HistoryItem[]; total: number };
			if (requestId !== this.requestId) return;
			if (trashed) {
				this.trashItems = data.items;
				this.trashTotal = data.total;
				if (!search) this.syncTrashPage(data.items.slice(0, 100), data.total);
			} else {
				this.activeItems = data.items;
				this.activeTotal = data.total;
			}
			this.preloadKey = this.cacheKey(view, page, pageSize, search, starredOnly, data.total);
			if (data.items.length === 0 && data.total > 0 && page > 0) {
				const fallbackPage = page - 1;
				this.page = fallbackPage;
				if (
					this.view === view &&
					this.search.trim() === search &&
					this.starredOnly === starredOnly
				) {
					await this.fetch({ view, page: fallbackPage, search, starredOnly });
				}
			}
		} catch { /* ignore */ }
		finally {
			this.pendingRequests = Math.max(0, this.pendingRequests - 1);
			if (!silent && (requestId === this.requestId || this.pendingRequests === 0)) this.loading = false;
		}
	};

	preloadFirstPage(activeItems: HistoryItem[], activeTotal: number, trashTotal: number, pageSize: number) {
		const nextPageSize = Math.max(1, Math.min(100, Math.floor(pageSize)));
		this.trashTotal = trashTotal;
		this.activeTotal = activeTotal;
		if (this.preloadMatches('active', 0, nextPageSize, '', false, activeTotal)) return;
		this.pageSize = nextPageSize;
		if (activeItems.length > this.activeItems.length) this.activeItems = activeItems;
		void this.fetch({ view: 'active', page: 0, search: '', starredOnly: false, pageSize: nextPageSize, silent: true });
	}

	primeFirstPage(activeItems: HistoryItem[], activeTotal: number, trashTotal: number, pageSize: number) {
		const nextPageSize = Math.max(1, Math.min(100, Math.floor(pageSize)));
		this.pageSize = nextPageSize;
		this.activeItems = activeItems;
		this.activeTotal = activeTotal;
		this.trashTotal = trashTotal;
		this.preloadKey = this.cacheKey('active', 0, nextPageSize, '', false, activeTotal);
	}

	setView = (view: HistoryManagerView) => {
		this.view = view;
		this.page = 0;
		this.selectedIds = [];
		void this.fetch({ view, page: 0 });
	};

	setStarredOnly = (value: boolean) => {
		this.starredOnly = value;
		this.page = 0;
		this.selectedIds = [];
		void this.fetch({ page: 0, starredOnly: value });
	};

	setPage = (page: number) => {
		const nextPage = Math.max(0, Math.min(page, this.totalPages - 1));
		if (nextPage === this.page) return;
		this.page = nextPage;
		this.selectedIds = [];
		void this.fetch({ page: nextPage });
	};

	setPageSize = (pageSize: number) => {
		const nextPageSize = Math.max(1, Math.min(200, Math.floor(pageSize)));
		if (nextPageSize === this.pageSize) {
			const expectedItems = Math.min(nextPageSize, this.total);
			if (this.items.length < expectedItems) void this.fetch({ page: this.page });
			return;
		}
		this.pageSize = nextPageSize;
		this.page = Math.max(0, Math.min(this.page, this.totalPages - 1));
		this.selectedIds = [];
		void this.fetch({ page: this.page });
	};

	searchChanged = (search: string) => {
		this.page = 0;
		this.selectedIds = [];
		void this.fetch({ page: 0, search });
	};

	toggleSelection(id: string) {
		this.selectedIds = this.selectedIds.includes(id)
			? this.selectedIds.filter((x) => x !== id)
			: [...this.selectedIds, id];
	}

	toggleSelectAll() {
		const ids = this.items.map((it) => it.id).filter((id): id is string => !!id);
		this.selectedIds = this.selectedIds.length === ids.length ? [] : ids;
	}

	applyStarState(item: { id?: string; starred?: boolean }) {
		if (!item.id) return;
		this.activeItems = this.activeItems.map((it) => it.id === item.id ? { ...it, starred: item.starred } : it);
		this.trashItems = this.trashItems.map((it) => it.id === item.id ? { ...it, starred: item.starred } : it);
		this.preloadKey = "";
	}

	private cacheKey(view: HistoryManagerView, page: number, pageSize: number, search: string, starredOnly: boolean, total: number): string {
		return [view, page, pageSize, search, starredOnly ? 1 : 0, total].join('|');
	}

	private preloadMatches(view: HistoryManagerView, page: number, pageSize: number, search: string, starredOnly: boolean, total: number): boolean {
		const expectedItems = Math.min(pageSize, total);
		return (
			this.preloadKey === this.cacheKey(view, page, pageSize, search, starredOnly, total) &&
			this.items.length >= expectedItems
		);
	}
}
