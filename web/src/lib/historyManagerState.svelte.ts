export const HISTORY_MANAGER_PAGE_SIZE = 100;

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
	render_color_catalog_id?: string | null;
	render_color_catalog_name?: string | null;
	render_color_catalog_sub?: string | null;
	render_color_map?: Record<string, string> | null;
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
};

export class HistoryManagerState {
	open = $state(false);
	view = $state<HistoryManagerView>('active');
	tab = $state<HistoryManagerTab>('thumbs');
	page = $state(0);
	loading = $state(false);
	starredOnly = $state(false);
	activeItems = $state<HistoryItem[]>([]);
	activeTotal = $state(0);
	trashItems = $state<HistoryItem[]>([]);
	trashTotal = $state(0);
	search = $state('');
	selectedIds = $state<string[]>([]);
	private requestId = 0;

	items = $derived(this.view === 'trash' ? this.trashItems : this.activeItems);
	total = $derived(this.view === 'trash' ? this.trashTotal : this.activeTotal);
	totalPages = $derived(Math.max(1, Math.ceil(this.total / HISTORY_MANAGER_PAGE_SIZE)));
	offset = $derived(this.page * HISTORY_MANAGER_PAGE_SIZE);
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
		this.loading = false;
		this.starredOnly = false;
		this.activeItems = [];
		this.activeTotal = 0;
		this.trashItems = [];
		this.trashTotal = 0;
		this.search = '';
		this.selectedIds = [];
		this.requestId += 1;
	}

	openWith(activeItems: HistoryItem[], activeTotal: number, trashTotal: number) {
		this.open = true;
		this.view = 'active';
		this.tab = 'thumbs';
		this.page = 0;
		this.search = '';
		this.selectedIds = [];
		this.activeItems = activeItems;
		this.activeTotal = activeTotal;
		this.trashItems = [];
		this.trashTotal = trashTotal;
		void this.fetch();
	}

	fetch = async (options: FetchOptions = {}): Promise<void> => {
		const requestId = ++this.requestId;
		const view = options.view ?? this.view;
		const page = options.page ?? this.page;
		const search = options.search ?? this.search.trim();
		const starredOnly = options.starredOnly ?? this.starredOnly;
		this.loading = true;
		try {
			const trashed = view === 'trash';
			const offset = page * HISTORY_MANAGER_PAGE_SIZE;
			const params = new URLSearchParams({
				offset: String(offset),
				limit: String(HISTORY_MANAGER_PAGE_SIZE),
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
			if (requestId === this.requestId) this.loading = false;
		}
	};

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
	}
}
