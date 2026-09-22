import type { PipelineHistoryDiagnostics } from '$lib/features/pipeline/diagnostics';

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
	pipeline_variation_id?: string | null;
	pipeline_revision?: string | null;
	pipeline_diagnostics?: PipelineHistoryDiagnostics;
	data_warnings?: string[];
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
	// v1.98: Expanded DDL (Stage 2 input). Works before v1.98 do not have it.
	expanded_ddl?: string | null;
	focus?: string | null;
	variation_amplitude?: string | null;
	variation_seed?: number | string | null;
	// v1.98: Why Stage 1 used its fallback. null means ordinary interpretation.
	interpret_fallback?: string | null;
	// Stage 2's counterpart, with a third reading the field above cannot make:
	// 'none' means a writer said the stage held, and an absent value means the
	// work was drawn before the column existed. See lib/composeFallback.ts.
	compose_fallback?: string | null;
	// Carried on a fresh paint result so a save can write the record above.
	// A work read back out of the listing has neither.
	compose_fallback_used?: boolean;
	compose_retry_reasons?: string[];
	thinking?: string | null;
	score: Score;
	svg: string;
	/** Stored SVG byte length, present even when list requests omit the SVG text. */
	svg_bytes?: number;
	at: number;
	elapsed_ms?: number;
	stage1_model?: string | null;
	stage2_model?: string | null;
	tokens_in?: number | null;
	tokens_out?: number | null;
	catalog_id?: string | null;
	// How the catalog was asked for (fixed / auto / random). Absent on works
	// saved before the column, which means "older than the field".
	catalog_mode?: string | null;
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
	// Sketch from life (Stage 0.5, v2.10). Absent on works made before the layer.
	sketch_text?: string | null;
	sketch_grain?: string | null;
	// What the layer did. Absent means the work predates the record, which is a
	// different thing from 'off'.
	sketch_state?: string | null;
	seed_text?: string | null;
	trashed?: boolean;
	starred?: boolean;
	for_revision?: boolean;
	// The share bit and where it points. Optional because a server that predates
	// them sends neither, which is a different thing from "not shared".
	for_share?: boolean;
	share_group_id?: string | null;
	note?: string | null;
};

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
type TrashPageSync = (items: HistoryItem[], total: number) => void;

/** What a request asks the server for. */
type Request = {
	view: HistoryManagerView;
	page: number;
	pageSize: number;
	/**
	 * Where in the listing the request starts, which is `page * pageSize`.
	 *
	 * Carried rather than recomputed because this is what two requests have to
	 * agree on to be the same question. `page` alone is not that: the same page
	 * number names a different place the moment the page size changes.
	 */
	offset: number;
	search: string;
	starredOnly: boolean;
	forRevisionOnly: boolean;
	forShareOnly: boolean;
};

type FetchOptions = {
	view?: HistoryManagerView;
	page?: number;
	search?: string;
	starredOnly?: boolean;
	forRevisionOnly?: boolean;
	forShareOnly?: boolean;
	pageSize?: number;
	silent?: boolean;
};

export class HistoryManagerState {
	open = $state(false);
	/** A library visit is an in-app round trip, not a fresh history session. */
	libraryInitialized = $state(false);
	selectionResetReason = $state<'query' | 'filter' | 'trash' | null>(null);
	view = $state<HistoryManagerView>('active');
	tab = $state<HistoryManagerTab>('thumbs');
	page = $state(0);
	pageSize = $state(HISTORY_MANAGER_DEFAULT_PAGE_SIZE);
	loading = $state(false);
	loadFailed = $state(false);
	starredOnly = $state(false);
	forRevisionOnly = $state(false);
	forShareOnly = $state(false);
	activeItems = $state<HistoryItem[]>([]);
	activeTotal = $state(0);
	trashItems = $state<HistoryItem[]>([]);
	trashTotal = $state(0);
	search = $state('');
	selectedIds = $state<string[]>([]);
	private requestId = 0;
	private pendingRequests = 0;
	private preloadKey = "";
	private stripSeedKey = "";
	private pageSizeMeasured = false;
	private awaitingInitialPageSize = false;
	private selectionResetTimer: number | null = null;
	private appliedSearch = '';
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
		this.loadFailed = false;
		this.starredOnly = false;
		this.forRevisionOnly = false;
		this.forShareOnly = false;
		this.activeItems = [];
		this.activeTotal = 0;
		this.trashItems = [];
		this.trashTotal = 0;
		this.search = '';
		this.selectedIds = [];
		this.requestId += 1;
		this.pendingRequests = 0;
		this.preloadKey = "";
		this.stripSeedKey = "";
		this.pageSizeMeasured = false;
		this.awaitingInitialPageSize = false;
		this.libraryInitialized = false;
		this.appliedSearch = '';
		this.clearSelectionResetNotice();
	}

	openWith(activeItems: HistoryItem[], activeTotal: number, trashTotal: number) {
		if (this.libraryInitialized) {
			this.open = true;
			// Reopening is a new permission-sensitive view of the same retained
			// query. Keep its query, page, checked ids, and scroll owner intact, but
			// replace the rows rather than presenting a stale cached result.
			void this.fetch({
				view: this.view,
				page: this.page,
				search: this.search.trim(),
				starredOnly: this.starredOnly,
				forRevisionOnly: this.forRevisionOnly,
				forShareOnly: this.forShareOnly,
			});
			return;
		}
		this.open = true;
		this.libraryInitialized = true;
		this.view = 'active';
		this.tab = 'thumbs';
		this.page = 0;
		this.search = '';
		this.selectedIds = [];
		this.appliedSearch = '';
		const stripSeedKey = this.cacheKey('active', 0, '', false, false, false, activeTotal);
		const hasFreshUnfilteredSeed =
			this.stripSeedKey === stripSeedKey &&
			this.preloadKey === stripSeedKey &&
			!this.starredOnly &&
			!this.forRevisionOnly &&
			!this.forShareOnly;
		const preloaded = this.preloadMatches(
			'active',
			0,
			this.pageSize,
			'',
			this.starredOnly,
			this.forRevisionOnly,
			this.forShareOnly,
			activeTotal
		);
		if (!preloaded && !hasFreshUnfilteredSeed) {
			this.activeItems = activeItems;
		}
		this.activeTotal = activeTotal;
		this.trashItems = [];
		this.trashTotal = trashTotal;
		// A fresh strip has already answered the first page's question. Let the
		// mounted grid report its actual capacity before deciding whether it needs
		// more; this replaces a guessed page request with one measured request.
		this.awaitingInitialPageSize = !preloaded && hasFreshUnfilteredSeed;
		if (!preloaded && !hasFreshUnfilteredSeed) {
			void this.fetch({ view: 'active', page: 0, pageSize: this.pageSize });
		}
	}

	fetch = async (options: FetchOptions = {}): Promise<void> => {
		const view = options.view ?? this.view;
		const page = options.page ?? this.page;
		const search = options.search ?? this.search.trim();
		const starredOnly = options.starredOnly ?? this.starredOnly;
		const forRevisionOnly = options.forRevisionOnly ?? this.forRevisionOnly;
		const forShareOnly = options.forShareOnly ?? this.forShareOnly;
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
		const offset = page * pageSize;
		const request: Request = { view, page, pageSize, offset, search, starredOnly, forRevisionOnly, forShareOnly };
		if (this.requestInFlight(request, pageSize)) return;
		const requestId = ++this.requestId;
		this.inFlight.push(request);
		this.pendingRequests += 1;
		if (!silent) this.loading = true;
		this.loadFailed = false;
		try {
			const trashed = view === 'trash';
			const params = new URLSearchParams({
				offset: String(offset),
				limit: String(pageSize),
				q: search,
				// The manager draws thumbnails, so it does not need the drawings.
				// They were nearly all of the cost: one page of them, 23.5 MB.
				include_svg: 'false',
			});
			if (trashed) params.set('trashed', 'true');
			if (starredOnly) params.set('starred', 'true');
			// The two marks are independent, so asking for both means both.
			if (forRevisionOnly) params.set('for_revision', 'true');
			// The third mark is independent of the other two in the same way.
			if (forShareOnly) params.set('for_share', 'true');
			const r = await this.apiFetch(`/api/history?${params.toString()}`);
			if (requestId !== this.requestId) return;
			if (!r.ok) {
				this.markLoadFailed(view);
				return;
			}
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
			// Written where the works are taken in, so the list identity and its
			// starting offset always move together.
			this.preloadKey = this.cacheKey(view, offset, search, starredOnly, forRevisionOnly, forShareOnly, data.total);
			if (data.items.length === 0 && data.total > 0 && page > 0) {
				const fallbackPage = page - 1;
				this.page = fallbackPage;
				if (
					this.view === view &&
					this.search.trim() === search &&
					this.starredOnly === starredOnly
					&& this.forRevisionOnly === forRevisionOnly
					&& this.forShareOnly === forShareOnly
				) {
					await this.fetch({ view, page: fallbackPage, search, starredOnly, forRevisionOnly, forShareOnly });
				}
			}
		} catch {
			if (requestId === this.requestId) this.markLoadFailed(view);
		}
		finally {
			this.inFlight = this.inFlight.filter((sent) => sent !== request);
			this.pendingRequests = Math.max(0, this.pendingRequests - 1);
			if (!silent && (requestId === this.requestId || this.pendingRequests === 0)) this.loading = false;
		}
	};

	retry = () => {
		void this.fetch({
			view: this.view,
			page: this.page,
			search: this.search.trim(),
			starredOnly: this.starredOnly,
			forRevisionOnly: this.forRevisionOnly,
			forShareOnly: this.forShareOnly,
		});
	};

	private markLoadFailed(view: HistoryManagerView): void {
		this.loadFailed = true;
		this.preloadKey = "";
		this.selectedIds = [];
		this.clearSelectionResetNotice();
		if (view === 'trash') {
			this.trashItems = [];
			this.trashTotal = 0;
		} else {
			this.activeItems = [];
			this.activeTotal = 0;
		}
	}

	/**
	 * Hand the manager what the history strip is holding.
	 *
	 * Two different quantities meet here and must not be confused. `pageSize` is
	 * how many works one page of the manager holds; `stripItems` is what the
	 * strip has just received for its visible first page. The mounted grid owns
	 * the decision whether that is enough, so its first measurement is the only
	 * point that starts a modal fetch.
	 */
	seedFromStrip(stripItems: HistoryItem[], activeTotal: number, trashTotal: number, pageSize: number) {
		// The strip is a first-open warm seed. Once the library has a retained
		// query, it must not replace that query's page while the modal is closed.
		if (this.libraryInitialized) return;
		if (!this.pageSizeMeasured) {
			this.pageSize = Math.max(1, Math.min(100, Math.floor(pageSize)));
		}
		this.activeTotal = activeTotal;
		this.trashTotal = trashTotal;
		const seedKey = this.cacheKey('active', 0, '', false, false, false, activeTotal);
		const keepsWarmPage =
			this.preloadKey === seedKey &&
			stripItems.every((item, index) => item.id === this.activeItems[index]?.id);
		if (!keepsWarmPage) this.activeItems = stripItems;
		this.preloadKey = seedKey;
		this.stripSeedKey = seedKey;
	}

	setView = (view: HistoryManagerView) => {
		this.awaitingInitialPageSize = false;
		this.view = view;
		this.page = 0;
		this.resetSelection('trash');
		void this.fetch({ view, page: 0 });
	};

	setStarredOnly = (value: boolean) => {
		this.awaitingInitialPageSize = false;
		this.starredOnly = value;
		this.page = 0;
		this.resetSelection('filter');
		void this.fetch({ page: 0, starredOnly: value });
	};

	setForRevisionOnly = (value: boolean) => {
		this.awaitingInitialPageSize = false;
		this.forRevisionOnly = value;
		this.page = 0;
		this.resetSelection('filter');
		void this.fetch({ page: 0, forRevisionOnly: value });
	};

	setForShareOnly = (value: boolean) => {
		this.awaitingInitialPageSize = false;
		this.forShareOnly = value;
		this.page = 0;
		this.resetSelection('filter');
		void this.fetch({ page: 0, forShareOnly: value });
	};

	setPage = (page: number) => {
		const nextPage = Math.max(0, Math.min(page, this.totalPages - 1));
		if (nextPage === this.page) return;
		this.awaitingInitialPageSize = false;
		this.page = nextPage;
		void this.fetch({ page: nextPage });
	};

	setPageSize = (pageSize: number) => {
		this.awaitingInitialPageSize = false;
		// `/api/history` accepts at most 100 rows. Keep the UI request valid even
		// when a very large grid has room for more cards than one server page.
		const nextPageSize = Math.max(1, Math.min(100, Math.floor(pageSize)));
		this.pageSize = nextPageSize;
		this.pageSizeMeasured = true;
		// Both quantities are computed here rather than read off the derived
		// fields: those are recomputed after this method returns, so reading them
		// now would clamp the page against the size that is being replaced.
		const nextTotalPages = Math.max(1, Math.ceil(this.total / nextPageSize));
		this.page = Math.max(0, Math.min(this.page, nextTotalPages - 1));
		// The grid's first measurement can be smaller than the page predicted
		// from the viewport. Its fresh strip page already answers that smaller
		// question, so only ask when the measured page needs items not in hand.
		// While a larger request is in flight, fetch() keeps the same protection.
		if (!this.preloadMatches(
			this.view,
			this.page,
			nextPageSize,
			this.search.trim(),
			this.starredOnly,
			this.forRevisionOnly,
			this.forShareOnly,
			this.total
		)) void this.fetch({ page: this.page });
	};

	searchChanged = (search: string) => {
		// The page re-runs its search effect whenever the manager opens, so this
		// arrives once per opening with the query the manager already has. That is
		// not a search, and answering it would cost a whole page of history for
		// works already in hand -- which is what reopening the manager used to do.
		const next = search.trim();
		// +page reports the empty bound value while the dynamically imported
		// manager is still mounting. It is not a user search, and must not turn
		// the fresh strip into a guessed-page request before the grid measures.
		if (!next && this.awaitingInitialPageSize) return;
		this.awaitingInitialPageSize = false;
		if (next === this.appliedSearch) return;
		this.appliedSearch = next;
		this.page = 0;
		this.resetSelection('query');
		if (this.preloadMatches(this.view, 0, this.pageSize, next, this.starredOnly, this.forRevisionOnly, this.forShareOnly, this.total)) return;
		void this.fetch({ page: 0, search });
	};

	clearSelection = () => {
		this.selectedIds = [];
		this.clearSelectionResetNotice();
	};

	private resetSelection(reason: 'query' | 'filter' | 'trash'): void {
		if (this.selectedIds.length === 0) return;
		this.selectedIds = [];
		this.selectionResetReason = reason;
		if (this.selectionResetTimer !== null) globalThis.clearTimeout(this.selectionResetTimer);
		this.selectionResetTimer = globalThis.setTimeout(() => {
			this.selectionResetReason = null;
			this.selectionResetTimer = null;
		}, 2400);
	}

	private clearSelectionResetNotice(): void {
		if (this.selectionResetTimer !== null) globalThis.clearTimeout(this.selectionResetTimer);
		this.selectionResetTimer = null;
		this.selectionResetReason = null;
	}

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

	applyForShareState(item: { id?: string; for_share?: boolean; share_group_id?: string | null }) {
		if (!item.id) return;
		// Both keys move together: the bit without its destination would leave the
		// row saying it is open with no record of to whom.
		const next = { for_share: item.for_share, share_group_id: item.share_group_id };
		this.activeItems = this.activeItems.map((it) => it.id === item.id ? { ...it, ...next } : it);
		this.trashItems = this.trashItems.map((it) => it.id === item.id ? { ...it, ...next } : it);
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
	 * `atLeast` is how many works the caller needs. A request for the same offset
	 * that asked for more of them answers a smaller need as well, which is the
	 * ordinary case on opening: the page guesses the manager's page size before
	 * the modal exists, then the modal measures its own grid and says a smaller
	 * number. Guessing 65 and measuring 52 must not cost two pages of history.
	 *
	 * Matched on `offset`, which is the place in the listing being asked for.
	 * `page` is not that place -- it is a place divided by a page size, and both
	 * halves move: the same page number with a different size names a different
	 * offset, and different page numbers with different sizes can name the same
	 * one. Matching on the number alone made a resize ride on a request for
	 * somewhere else, so the works that arrived were 36 short of the ones the
	 * modal then said it was showing.
	 */
	private requestInFlight(request: Request, atLeast: number): boolean {
		return this.inFlight.some((sent) =>
			sent.view === request.view &&
			sent.offset === request.offset &&
			sent.search === request.search &&
			sent.starredOnly === request.starredOnly &&
			sent.forRevisionOnly === request.forRevisionOnly &&
			sent.forShareOnly === request.forShareOnly &&
			sent.pageSize >= atLeast
		);
	}

	private cacheKey(view: HistoryManagerView, offset: number, search: string, starredOnly: boolean, forRevisionOnly: boolean, forShareOnly: boolean, total: number): string {
		return [view, offset, search, starredOnly ? 1 : 0, forRevisionOnly ? 1 : 0, forShareOnly ? 1 : 0, total].join('|');
	}

	/**
	 * Whether a whole page of what is being asked for is already in hand.
	 *
	 * Public because it is what decides whether opening the manager costs a
	 * fetch, which is a fact about this class rather than an internal detail.
	 */
	preloadMatches(view: HistoryManagerView, page: number, pageSize: number, search: string, starredOnly: boolean, forRevisionOnly: boolean, forShareOnly: boolean, total: number): boolean {
		const held = view === 'trash' ? this.trashItems : this.activeItems;
		const offset = page * pageSize;
		const expectedItems = Math.max(0, Math.min(pageSize, total - offset));
		return (
			this.preloadKey === this.cacheKey(view, offset, search, starredOnly, forRevisionOnly, forShareOnly, total) &&
			held.length >= expectedItems
		);
	}
}
