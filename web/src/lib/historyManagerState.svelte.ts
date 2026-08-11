export const HISTORY_MANAGER_DEFAULT_PAGE_SIZE = 24;

export type HistoryManagerView = 'active' | 'trash';
export type HistoryManagerTab = 'thumbs' | 'list';

export type Score = { instructions: unknown[]; canvas?: string | null };

export type HistoryItem = {
	// Set only when the work is somebody else's, reached through a group scope
	// or an explicit grant. Absent for one's own, so nothing changes for a
	// listing of works the caller made.
	shared?: boolean;
	id?: string;
	input: string;
	source_text?: string | null;
	display_label?: string | null;
	batch_line_number?: number | null;
	batch_run_id?: string | null;
	description_hash?: string | null;
	history_visibility?: 'normal' | 'lineage_only';
	lineage_node_id?: string | null;
	lineage_root_node_id?: string | null;
	lineage_generation?: number | null;
	lineage_state?: 'active' | 'lineage_only' | 'tombstone' | null;
	lineage_parent_node_id?: string | null;
	derivation_kind?: string | null;
	derivation_metadata?: Record<string, unknown>;
	ddl: string | null;
	// v1.98: 展開後 DDL (Stage 2 入力)。v1.98 以前の作品は持たない。
	expanded_ddl?: string | null;
	focus?: string | null;
	variation_amplitude?: string | null;
	variation_seed?: number | string | null;
	// v1.98: Stage 1 フォールバックで描かれた作品の理由。null = 通常の解釈。
	interpret_fallback?: string | null;
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
	render_engine_id?: string | null;
	render_engine_version?: string | null;
	ddl_version?: string | null;
	ddl_engine_version?: string | null;
	render_color_catalog_id?: string | null;
	render_color_catalog_name?: string | null;
	render_color_catalog_sub?: string | null;
	render_color_map?: Record<string, string> | null;
	render_canvas_aspect?: string | null;
	render_canvas_aspect_id?: string | null;
	render_canvas_aspect_ratio?: number | null;
	instruction_lang_requested?: string | null;
	instruction_lang_resolved?: string | null;
	ui_lang?: string | null;
	render_hash?: string | null;
	render_hash_short?: string | null;
	render_seed?: number | string | null;
	render_wild?: boolean | null;
	// The staffage level, on works saved before the axis was folded away
	// (v2.11.0). Nothing sets it any more; it is read so a past work can still
	// report the conditions it was drawn under.
	tenkei?: string | null;
	composition_seed?: number | string | null;
	interpretation_seed?: string | null;
	// 写生 (Stage 0.5, v2.10). Absent on every work made before the layer.
	sketch_text?: string | null;
	sketch_grain?: string | null;
	// What the layer did. Absent means the work predates the record, which is a
	// different thing from 'off'.
	sketch_state?: string | null;
	seed_text?: string | null;
	trashed?: boolean;
	starred?: boolean;
	for_revision?: boolean;
	note?: string | null;
};

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type TrashPageSync = (items: HistoryItem[], total: number) => void;

/** What a request asks the server for. */
type Request = {
	view: HistoryManagerView;
	page: number;
	pageSize: number;
	search: string;
	starredOnly: boolean;
	forRevisionOnly: boolean;
};

type FetchOptions = {
	view?: HistoryManagerView;
	page?: number;
	search?: string;
	starredOnly?: boolean;
	forRevisionOnly?: boolean;
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
	forRevisionOnly = $state(false);
	activeItems = $state<HistoryItem[]>([]);
	activeTotal = $state(0);
	trashItems = $state<HistoryItem[]>([]);
	trashTotal = $state(0);
	search = $state('');
	selectedIds = $state<string[]>([]);
	private requestId = 0;
	private pendingRequests = 0;
	private preloadKey = "";
	// Requests that have been sent and not yet come back. One page of history is
	// tens of megabytes here, so asking again for something already on its way is
	// not a harmless duplicate.
	private inFlight: Request[] = [];

	// One page shows what fits and no more. The works in hand can outnumber it:
	// the page guesses the manager's page size before the modal exists and fetches
	// with the guess, then the modal measures its own grid and says a smaller
	// number. Drawing the surplus does not show it -- the grid's box clips what
	// overflows -- while `offset` advances by pageSize, so the next page would
	// hand back works already counted as shown. Capping here keeps the quantity
	// that is drawn and the quantity that `offset` steps by the same one.
	items = $derived(this.pageOf(this.view === 'trash' ? this.trashItems : this.activeItems));
	total = $derived(this.view === 'trash' ? this.trashTotal : this.activeTotal);
	totalPages = $derived(Math.max(1, Math.ceil(this.total / this.pageSize)));
	offset = $derived(this.page * this.pageSize);
	shownTo = $derived(Math.min(this.offset + this.items.length, this.total));

	// Written out rather than declared as constructor parameter properties: node's
	// strip-only TypeScript loader cannot parse that form, and the unit tests
	// construct this class for real.
	private readonly apiFetch: ApiFetch;
	private readonly syncTrashPage: TrashPageSync;

	constructor(apiFetch: ApiFetch, syncTrashPage: TrashPageSync) {
		this.apiFetch = apiFetch;
		this.syncTrashPage = syncTrashPage;
	}

	/**
	 * One page's worth of the works in hand.
	 *
	 * Public, and a method rather than part of the $derived above, because this
	 * is where the quantity that is shown is decided, and it has to be the same
	 * quantity `offset` advances by. A rune is a compile-time transform, so a
	 * test outside the browser cannot evaluate it; leaving the decision inside
	 * one would leave the gates reading their own stand-in for it instead.
	 */
	pageOf(held: HistoryItem[]): HistoryItem[] {
		return held.slice(0, this.pageSize);
	}

	clear() {
		this.open = false;
		this.view = 'active';
		this.tab = 'thumbs';
		this.page = 0;
		this.pageSize = HISTORY_MANAGER_DEFAULT_PAGE_SIZE;
		this.loading = false;
		this.starredOnly = false;
		this.forRevisionOnly = false;
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
		const preloaded = this.preloadMatches('active', 0, this.pageSize, '', false, false, activeTotal);
		if (!preloaded) {
			this.activeItems = activeItems;
		}
		this.activeTotal = activeTotal;
		this.trashItems = [];
		this.trashTotal = trashTotal;
		// The first load carries the strip's works only, so a full page has to be
		// fetched by whoever opens the manager. Seeded items stay on screen while
		// it arrives. When a page is already in hand, opening costs nothing.
		if (!preloaded) void this.fetch({ view: 'active', page: 0, pageSize: this.pageSize });
	}

	fetch = async (options: FetchOptions = {}): Promise<void> => {
		const view = options.view ?? this.view;
		const page = options.page ?? this.page;
		const search = options.search ?? this.search.trim();
		const starredOnly = options.starredOnly ?? this.starredOnly;
		const forRevisionOnly = options.forRevisionOnly ?? this.forRevisionOnly;
		const pageSize = options.pageSize ?? this.pageSize;
		const silent = options.silent ?? false;
		// Two callers can decide at the same moment that the manager needs its
		// page -- opening it is one, the page's search effect another. Asking
		// twice costs a second copy of the same tens of megabytes and shows the
		// user nothing extra, so the later caller rides on the request already
		// out. Answers still arrive; only the duplicate question is dropped.
		//
		// This has to be decided before taking a request number. A number marks
		// every earlier request as superseded, so a question dropped after taking
		// one would throw away the answer it was riding on: the works arrive, all
		// of them, and are discarded on the doorstep.
		const request: Request = { view, page, pageSize, search, starredOnly, forRevisionOnly };
		if (this.requestInFlight(request, pageSize)) return;
		const requestId = ++this.requestId;
		this.inFlight.push(request);
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
			// The two marks are independent, so asking for both means both.
			if (forRevisionOnly) params.set('for_revision', 'true');
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
			this.preloadKey = this.cacheKey(view, page, pageSize, search, starredOnly, forRevisionOnly, data.total);
			if (data.items.length === 0 && data.total > 0 && page > 0) {
				const fallbackPage = page - 1;
				this.page = fallbackPage;
				if (
					this.view === view &&
					this.search.trim() === search &&
					this.starredOnly === starredOnly
					&& this.forRevisionOnly === forRevisionOnly
				) {
					await this.fetch({ view, page: fallbackPage, search, starredOnly, forRevisionOnly });
				}
			}
		} catch { /* ignore */ }
		finally {
			this.inFlight = this.inFlight.filter((sent) => sent !== request);
			this.pendingRequests = Math.max(0, this.pendingRequests - 1);
			if (!silent && (requestId === this.requestId || this.pendingRequests === 0)) this.loading = false;
		}
	};

	preloadFirstPage(activeItems: HistoryItem[], activeTotal: number, trashTotal: number, pageSize: number) {
		const nextPageSize = Math.max(1, Math.min(100, Math.floor(pageSize)));
		this.trashTotal = trashTotal;
		this.activeTotal = activeTotal;
		if (this.preloadMatches('active', 0, nextPageSize, '', false, false, activeTotal)) return;
		this.pageSize = nextPageSize;
		if (activeItems.length > this.activeItems.length) this.activeItems = activeItems;
		void this.fetch({ view: 'active', page: 0, search: '', starredOnly: false, forRevisionOnly: false, pageSize: nextPageSize, silent: true });
	}

	/**
	 * Hand the manager what the history strip is holding.
	 *
	 * Two different quantities meet here and must not be confused. `pageSize` is
	 * how many works one page of the manager holds; `stripItems` is what the
	 * strip happens to have in hand, which is fewer -- the strip asks only for
	 * what it shows. The items are kept so the modal does not open blank, but
	 * they are not a page, so no preload key is written and openWith() will go
	 * and fetch one. Items already in hand are not replaced by a shorter list.
	 */
	seedFromStrip(stripItems: HistoryItem[], activeTotal: number, trashTotal: number, pageSize: number) {
		this.pageSize = Math.max(1, Math.min(100, Math.floor(pageSize)));
		this.activeTotal = activeTotal;
		this.trashTotal = trashTotal;
		if (stripItems.length > this.activeItems.length) this.activeItems = stripItems;
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

	setForRevisionOnly = (value: boolean) => {
		this.forRevisionOnly = value;
		this.page = 0;
		this.selectedIds = [];
		void this.fetch({ page: 0, forRevisionOnly: value });
	};

	setPage = (page: number) => {
		const nextPage = Math.max(0, Math.min(page, this.totalPages - 1));
		if (nextPage === this.page) return;
		this.page = nextPage;
		void this.fetch({ page: nextPage });
	};

	setPageSize = (pageSize: number) => {
		const nextPageSize = Math.max(1, Math.min(200, Math.floor(pageSize)));
		this.pageSize = nextPageSize;
		this.page = Math.max(0, Math.min(this.page, this.totalPages - 1));
		// The modal measures itself once it is on screen and reports the real page
		// size, which arrives while the page opened with is still being fetched.
		// Nothing is asked for here: fetch() sees that the answer on its way holds
		// at least this many works and drops the question.
		const expectedItems = Math.min(nextPageSize, this.total);
		if (this.items.length < expectedItems) void this.fetch({ page: this.page });
	};

	searchChanged = (search: string) => {
		// The page re-runs its search effect whenever the manager opens, so this
		// arrives once per opening with the query the manager already has. That is
		// not a search, and answering it would cost a whole page of history for
		// works already in hand -- which is what reopening the manager used to do.
		const next = search.trim();
		if (this.preloadMatches(this.view, 0, this.pageSize, next, this.starredOnly, this.forRevisionOnly, this.total)) return;
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
		const pageIds = new Set(ids);
		const allPageItemsSelected = ids.length > 0 && ids.every((id) => this.selectedIds.includes(id));
		this.selectedIds = allPageItemsSelected
			? this.selectedIds.filter((id) => !pageIds.has(id))
			: [...this.selectedIds, ...ids.filter((id) => !this.selectedIds.includes(id))];
	}

	applyForRevisionState(item: { id?: string; for_revision?: boolean }) {
		if (!item.id) return;
		this.activeItems = this.activeItems.map((it) => it.id === item.id ? { ...it, for_revision: item.for_revision } : it);
		this.trashItems = this.trashItems.map((it) => it.id === item.id ? { ...it, for_revision: item.for_revision } : it);
		this.preloadKey = "";
	}

	applyStarState(item: { id?: string; starred?: boolean; note?: string | null }) {
		if (!item.id) return;
		const hasNote = Object.prototype.hasOwnProperty.call(item, "note");
		this.activeItems = this.activeItems.map((it) => it.id === item.id ? { ...it, starred: item.starred, note: hasNote ? item.note : it.note } : it);
		this.trashItems = this.trashItems.map((it) => it.id === item.id ? { ...it, starred: item.starred, note: hasNote ? item.note : it.note } : it);
		this.preloadKey = "";
	}

	/**
	 * Whether a request already on its way will answer this one.
	 *
	 * `atLeast` is how many works the caller needs. A request for the same page
	 * that asked for more of them answers a smaller need as well, which is the
	 * ordinary case on opening: the page guesses the manager's page size before
	 * the modal exists, then the modal measures its own grid and says a smaller
	 * number. Guessing 65 and measuring 52 must not cost two pages of history.
	 */
	private requestInFlight(request: Request, atLeast: number): boolean {
		return this.inFlight.some((sent) =>
			sent.view === request.view &&
			sent.page === request.page &&
			sent.search === request.search &&
			sent.starredOnly === request.starredOnly &&
			sent.forRevisionOnly === request.forRevisionOnly &&
			sent.pageSize >= atLeast
		);
	}

	private cacheKey(view: HistoryManagerView, page: number, pageSize: number, search: string, starredOnly: boolean, forRevisionOnly: boolean, total: number): string {
		return [view, page, pageSize, search, starredOnly ? 1 : 0, forRevisionOnly ? 1 : 0, total].join('|');
	}

	/**
	 * Whether a whole page of what is being asked for is already in hand.
	 *
	 * Public because it is what decides whether opening the manager costs a
	 * fetch, which is a fact about this class rather than an internal detail.
	 */
	preloadMatches(view: HistoryManagerView, page: number, pageSize: number, search: string, starredOnly: boolean, forRevisionOnly: boolean, total: number): boolean {
		const expectedItems = Math.min(pageSize, total);
		return (
			this.preloadKey === this.cacheKey(view, page, pageSize, search, starredOnly, forRevisionOnly, total) &&
			this.items.length >= expectedItems
		);
	}
}
