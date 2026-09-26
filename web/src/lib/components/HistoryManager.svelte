<script lang="ts">
	import Tooltip from './Tooltip.svelte';
	import { onMount, untrack } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import HistoryThumbnail from '$lib/components/HistoryThumbnail.svelte';
	import SavedWorkExportMenu from '$lib/components/SavedWorkExportMenu.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { SheetVariant } from '$lib/contactSheet';
	import type { SvgProfile } from '$lib/features/export/download';
	import type { SavedWorkExportItem, SavedWorkExportScope, SavedWorkExportSnapshot } from '$lib/features/export/saved-work';
	import { formatByteSize, groupDigits } from '$lib/formatNumber';
	import { formatHistoryMinute, historyListDescription } from '$lib/historyManagerPresentation';
	import { historyGridPageSize } from '$lib/historyManagerSizing';
	import { getCanvasAspectOption } from '$lib/plugins/system/canvas-aspect';
	import HistoryDescription from '$lib/components/HistoryDescription.svelte';

	type HistoryItem = {
		// Set only when the work is somebody else's, reached through a group
		// scope or an explicit grant. Absent for one's own.
		shared?: boolean;
		has_acl_shares?: boolean;
		id?: string;
		input: string;
		source_text?: string | null;
		display_label?: string | null;
		lineage_generation?: number | null;
		ddl: string | null;
		thinking?: string | null;
		score: { instructions: unknown[] };
		svg: string;
		svg_bytes?: number;
		at: number;
		elapsed_ms?: number;
		stage1_model?: string | null;
		stage2_model?: string | null;
		tokens_in?: number | null;
		tokens_out?: number | null;
		catalog_id?: string | null;
		render_hash?: string | null;
		render_hash_short?: string | null;
		render_build_number?: string | null;
		render_engine_id?: string | null;
		render_engine_version?: string | null;
		render_color_catalog_id?: string | null;
		render_color_catalog_name?: string | null;
		render_color_catalog_sub?: string | null;
		render_canvas_aspect_id?: string | null;
		render_canvas_aspect?: string | null;
		render_canvas_aspect_ratio?: number | null;
		variation_amplitude?: string | null;
		variation_seed?: number | string | null;
		render_seed?: number | string | null;
		composition_seed?: number | string | null;
	interpretation_seed?: string | null;
	lineage_node_id?: string | null;
	lineage_root_node_id?: string | null;
		trashed?: boolean;
		starred?: boolean;
		for_revision?: boolean;
		for_share?: boolean;
		share_group_id?: string | null;
	note?: string | null;
	};

	type LineageHistoryGroup = { root_node_id: string; representative: HistoryItem; item_count: number; starred_count: number; for_revision_count: number; latest_at: number };
	type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

	type Props = {
		/** Kept mounted between library visits so its list, scroll, and preview survive. */
		active: boolean;
		historyManagerView: 'active' | 'trash';
		historyManagerTab: 'thumbs' | 'list';
		historyManagerPage: number;
		historyManagerLoading: boolean;
		historyManagerLoadFailed: boolean;
		historyManagerTotalPages: number;
		historyManagerOffset: number;
		historyManagerShownTo: number;
		managedHistoryItems: HistoryItem[];
		managedHistoryTotal: number;
		// One source for how many works are in the trash. The page holds it and
		// both routes that learn a new count write it there.
		trashTotal: number;
		selectedHistoryIds: string[];
		animationExportSettings: AnimationExportSettings;
		pngTemplates?: ExportTemplate[];
		onDownloadSavedWorkSVG?: (profile: SvgProfile, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkPNG?: (height: number, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkCard?: (historyId: string, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkDdl?: (snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkAnimation: (snapshot: SavedWorkExportSnapshot, settings: AnimationExportSettings, directory?: FileSystemDirectoryHandle) => void | Promise<void>;
		onDownloadSavedWorkContactSheet: (snapshot: SavedWorkExportSnapshot, variant: SheetVariant) => void | Promise<void>;
		onValidateSavedWorkExport: (snapshot: SavedWorkExportSnapshot) => boolean | Promise<boolean>;
		historySearch: string;
		historyManagerStarredOnly: boolean;
		historyManagerForRevisionOnly: boolean;
		historyManagerForShareOnly: boolean;
		selectionResetReason?: 'query' | 'filter' | 'trash' | null;
		onClose: () => void;
		onSetView: (view: 'active' | 'trash') => void;
		onSetPage: (page: number) => void;
		onSetLatestPage: () => void | Promise<void>;
		onSetFirstPage: () => void | Promise<void>;
		onSetPageSize: (pageSize: number) => void;
		onRetryLoad: () => void;
		onSetStarredOnly: (value: boolean) => void;
		onSetForRevisionOnly: (value: boolean) => void;
		onSetForShareOnly: (value: boolean) => void;
		onToggleForRevision: (item: HistoryItem, event?: Event) => void | Promise<void>;
		onSelectAll: () => void;
		onAskTrash: (ids: string[]) => void;
		onAskRestore: (ids: string[]) => void;
		onAskPermanentDelete: (ids: string[]) => void;
		onToggleSelection: (id: string) => void;
		onOpenArtwork: (item: HistoryItem) => void;
		onOpenLineage: (item: HistoryItem) => void;
		onRefine: (item: HistoryItem) => void;
		onToggleStar: (item: HistoryItem, event?: Event) => void | Promise<void>;
		// Absent in single-user mode, where there is nobody to share with.
		onShareItem?: ((item: HistoryItem) => void) | null;
		aclShareStatus?: Record<string, boolean>;
		groupShareStatus?: Record<string, boolean>;
		isJapanese?: boolean;
		historyModelFull: (model: string) => string;
		formatHistoryDate: (at: number) => string;
		catalogName: (id: string | null | undefined) => string;
		historyPreviewText: (text: string) => string;
		shortModel: (model: string | null | undefined) => string;
		apiFetch: ApiFetch;
		currentHistoryId?: string | null;
		currentLineageRootId?: string | null;
	};

	let {
		active,
		historyManagerView,
		historyManagerTab = $bindable('thumbs'),
		historyManagerPage,
		historyManagerLoading,
		historyManagerLoadFailed,
		historyManagerTotalPages,
		historyManagerOffset,
		historyManagerShownTo,
		managedHistoryItems,
		managedHistoryTotal,
		trashTotal,
		selectedHistoryIds,
		animationExportSettings,
		pngTemplates = [],
		onDownloadSavedWorkSVG,
		onDownloadSavedWorkPNG,
		onDownloadSavedWorkCard, onDownloadSavedWorkDdl,
		onDownloadSavedWorkAnimation,
		onDownloadSavedWorkContactSheet,
		onValidateSavedWorkExport,
		historySearch = $bindable(''),
		historyManagerStarredOnly,
		historyManagerForRevisionOnly,
		historyManagerForShareOnly,
		selectionResetReason = null,
		onClose,
		onSetView,
		onSetPage,
		onSetLatestPage,
		onSetFirstPage,
		onSetPageSize,
		onRetryLoad,
		onSetStarredOnly,
		onSetForRevisionOnly,
		onSetForShareOnly,
		onToggleForRevision,
		onSelectAll,
		onAskTrash,
		onAskRestore,
		onAskPermanentDelete,
		onToggleSelection,
		onOpenArtwork,
		onOpenLineage,
		onRefine,
		onToggleStar,
		onShareItem = null,
		aclShareStatus = {},
		groupShareStatus = {},
		isJapanese = false,
		historyModelFull,
		formatHistoryDate,
		catalogName,
		historyPreviewText,
		shortModel,
		apiFetch,
		currentHistoryId = null,
		currentLineageRootId = null
	}: Props = $props();

	function hasAclShares(item: HistoryItem): boolean {
		return item.id && Object.hasOwn(aclShareStatus, item.id)
			? aclShareStatus[item.id]
			: !!item.has_acl_shares;
	}

	function isGroupShared(item: HistoryItem): boolean {
		return item.id && Object.hasOwn(groupShareStatus, item.id)
			? groupShareStatus[item.id]
			: !!item.for_share;
	}

	let thumbGridWrapEl = $state<HTMLDivElement | null>(null);
	let historyDisplayMode = $state<'chronological' | 'lineage'>('chronological');
	let lineageGroups = $state<LineageHistoryGroup[]>([]);
	let lineageGroupTotal = $state(0);
	let lineageGroupPage = $state(0);
	let lineageGroupLoading = $state(false);
	let lineageLoadFailed = $state(false);
	let expandedRootIds = $state<string[]>([]);
	let lineageGroupItems = $state<Record<string, HistoryItem[]>>({});
	let lineageMemberLoadingIds = $state<string[]>([]);
	let lineageRequestId = 0;
	let lineageGroupController: AbortController | null = null;
	const lineageMemberControllers = new Map<string, AbortController>();
	let copiedHistoryHash = $state<string | null>(null);
	let previewItem = $state<HistoryItem | null>(null);
	let previewLoading = $state(false);
	let previewError = $state(false);
	let previewRequestId = 0;
	let previewController: AbortController | null = null;
	let previewReturnElement: HTMLElement | null = null;
	let selectedExportItems = $state<Record<string, SavedWorkExportItem>>({});
	const checkedExportScope = $derived.by((): SavedWorkExportScope | null => {
		if (historyManagerView !== 'active' || selectedHistoryIds.length === 0) return null;
		const works = selectedHistoryIds.map((id) => selectedExportItems[id]);
		// A selection can outlive its visible page. It must be complete before the
		// menu takes a snapshot: exporting the page-local subset would be wrong.
		if (works.some((work) => !work)) return null;
		return { kind: 'selection', works: works as SavedWorkExportItem[] };
	});
	const previewReady = $derived(active && historyManagerView === 'active' && !!previewItem && !previewLoading && !previewError);
	const previewExportScope = $derived.by((): SavedWorkExportScope | null => {
		if (!previewReady || !previewItem?.id) return null;
		return {
			kind: 'current',
			works: [{ id: previewItem.id, at: previewItem.at, trashed: previewItem.trashed }],
		};
	});

	function exportItem(item: HistoryItem): SavedWorkExportItem | null {
		return item.id ? {
			id: item.id,
			at: item.at,
			trashed: item.trashed,
			description: item.source_text ?? item.input,
			preview: item.svg || null,
		} : null;
	}

	function rememberExportItem(item: HistoryItem): void {
		const work = exportItem(item);
		if (work) selectedExportItems = { ...selectedExportItems, [work.id]: work };
	}

	function toggleSelection(item: HistoryItem): void {
		if (!item.id) return;
		if (!selectedHistoryIds.includes(item.id)) rememberExportItem(item);
		onToggleSelection(item.id);
	}

	function selectAllVisible(): void {
		for (const item of managedHistoryItems) rememberExportItem(item);
		for (const item of Object.values(lineageGroupItems).flat()) rememberExportItem(item);
		onSelectAll();
	}

	function sameExportItems(left: Record<string, SavedWorkExportItem>, right: Record<string, SavedWorkExportItem>): boolean {
		const leftIds = Object.keys(left);
		return leftIds.length === Object.keys(right).length
			&& leftIds.every((id) => left[id].at === right[id]?.at && left[id].trashed === right[id]?.trashed);
	}

	$effect(() => {
		const selected = new Set(selectedHistoryIds);
		const visible = [
			...managedHistoryItems,
			...Object.values(lineageGroupItems).flat(),
		];
		const next: Record<string, SavedWorkExportItem> = {};
		for (const id of selected) {
			const item = visible.find((candidate) => candidate.id === id);
			const work = item ? exportItem(item) : selectedExportItems[id];
			if (work) next[id] = work;
		}
		if (!sameExportItems(selectedExportItems, next)) selectedExportItems = next;
	});
	let copiedHistoryHashTimer: number | null = null;
	const lineageGroupPageSize = 8;
	const lineageGroupTotalPages = $derived(Math.max(1, Math.ceil(lineageGroupTotal / lineageGroupPageSize)));

	onMount(() => {
		try {
			if (localStorage.getItem('inku-history-display-mode') === 'lineage') historyDisplayMode = 'lineage';
		} catch {}
		return () => {
			previewController?.abort();
			lineageGroupController?.abort();
			for (const controller of lineageMemberControllers.values()) controller.abort();
			if (copiedHistoryHashTimer !== null) window.clearTimeout(copiedHistoryHashTimer);
		};
	});

	function setHistoryDisplayMode(mode: 'chronological' | 'lineage') {
		historyDisplayMode = mode;
		lineageGroupPage = 0;
		expandedRootIds = [];
		try { localStorage.setItem('inku-history-display-mode', mode); } catch {}
	}

	// The thumbnail tab and the list tab page over different sets in lineage mode
	// (the thumbnail tab asks for min_items=2), so an offset carried across the
	// switch would land on a page that does not exist in the other set.
	function selectHistoryManagerTab(tab: 'thumbs' | 'list') {
		if (tab === historyManagerTab) return;
		historyManagerTab = tab;
		if (historyDisplayMode === 'lineage') {
			lineageGroupPage = 0;
			expandedRootIds = [];
		}
	}

	function recordedModel(model: string | null | undefined): string | null {
		return model && model.trim() ? model : null;
	}

	function modelLines(item: HistoryItem): { label: string | null; compact: string; full: string }[] {
		const interpretation = recordedModel(item.stage1_model);
		const drawing = recordedModel(item.stage2_model);
		if (interpretation && drawing && interpretation === drawing) {
			return [{ label: null, compact: shortModel(interpretation), full: historyModelFull(interpretation) }];
		}
		return [
			{ label: t().historyModelInterpretation, compact: interpretation ? shortModel(interpretation) : t().historyModelUnrecorded, full: interpretation ? historyModelFull(interpretation) : t().historyModelUnrecorded },
			{ label: t().historyModelDrawing, compact: drawing ? shortModel(drawing) : t().historyModelUnrecorded, full: drawing ? historyModelFull(drawing) : t().historyModelUnrecorded }
		];
	}

	const lineageThumbsMode = $derived(
		historyDisplayMode === 'lineage' && historyManagerTab === 'thumbs',
	);

	// Generation order, not time order: the point of laying a lineage out is to
	// show what came from what, and a sibling made later than its cousin would
	// otherwise sit between a parent and its child. `at` breaks ties inside a
	// generation, and a work with no recorded generation sorts to the front so it
	// never hides between two numbered ones.
	function membersInGenerationOrder(items: HistoryItem[] | undefined): HistoryItem[] {
		return [...(items ?? [])].sort(
			(a, b) =>
				(a.lineage_generation ?? 0) - (b.lineage_generation ?? 0)
				|| (a.at ?? 0) - (b.at ?? 0),
		);
	}

	function lineageLaneItems(group: LineageHistoryGroup): HistoryItem[] {
		const ordered = membersInGenerationOrder(lineageGroupItems[group.root_node_id]);
		const rootIndex = ordered.findIndex((item) => item.lineage_node_id === group.root_node_id);
		if (rootIndex <= 0) return ordered;
		return [ordered[rootIndex], ...ordered.slice(0, rootIndex), ...ordered.slice(rootIndex + 1)];
	}

	async function fetchLineageGroups(): Promise<void> {
		if (!active) return;
		const requestId = ++lineageRequestId;
		lineageGroupController?.abort();
		const controller = new AbortController();
		lineageGroupController = controller;
		lineageGroupLoading = true;
		lineageLoadFailed = false;
		const params = new URLSearchParams({ offset: String(lineageGroupPage * lineageGroupPageSize), limit: String(lineageGroupPageSize), q: historySearch.trim() });
		if (historyManagerView === 'trash') params.set('trashed', 'true');
		if (historyManagerStarredOnly) params.set('starred', 'true');
		if (historyManagerForRevisionOnly) params.set('for_revision', 'true');
		if (historyManagerForShareOnly) params.set('for_share', 'true');
		// The thumbnail tab lays a lineage's works out side by side, so a lineage
		// holding one work has nothing to lay out. The server drops them, because
		// dropping them here would leave short pages and a total that disagrees.
		if (lineageThumbsMode) params.set('min_items', '2');
		try {
			const response = await apiFetch('/api/history/lineage-groups?' + params.toString(), { cache: 'no-store', signal: controller.signal });
			if (!response.ok) throw new Error('HTTP ' + response.status);
			const data = await response.json() as { groups: LineageHistoryGroup[]; total: number };
			if (!active || requestId !== lineageRequestId) return;
			lineageGroups = data.groups;
			lineageGroupTotal = data.total;
			lineageGroupItems = {};
			expandedRootIds = [];
			if (lineageThumbsMode) {
				// The works are the point of this view, so they load with the page
				// instead of waiting for a click on every group.
				expandedRootIds = data.groups.map((group) => group.root_node_id);
				await Promise.all(data.groups.map((group) => loadLineageMembers(group.root_node_id)));
			}
		} catch (error) {
			if (!(error instanceof DOMException && error.name === 'AbortError') && requestId === lineageRequestId) {
				lineageLoadFailed = true;
				lineageGroups = [];
				lineageGroupTotal = 0;
				lineageGroupItems = {};
				expandedRootIds = [];
				clearPreview();
			}
		} finally {
			if (requestId === lineageRequestId) lineageGroupLoading = false;
			if (lineageGroupController === controller) lineageGroupController = null;
		}
	}

	async function toggleLineageGroup(rootNodeId: string): Promise<void> {
		if (expandedRootIds.includes(rootNodeId)) {
			expandedRootIds = expandedRootIds.filter((id) => id !== rootNodeId);
			return;
		}
		expandedRootIds = [...expandedRootIds, rootNodeId];
		if (lineageGroupItems[rootNodeId]) return;
		await loadLineageMembers(rootNodeId);
	}

	async function loadLineageMembers(rootNodeId: string): Promise<void> {
		if (!active) return;
		if (lineageGroupItems[rootNodeId]) return;
		lineageMemberLoadingIds = [...lineageMemberLoadingIds, rootNodeId];
		lineageMemberControllers.get(rootNodeId)?.abort();
		const controller = new AbortController();
		lineageMemberControllers.set(rootNodeId, controller);
		// Thumbnails, like the listing: a whole lineage with every SVG in it could
		// run to hundreds of megabytes. A preview reads its one SVG when opened.
		const params = new URLSearchParams({ limit: '10000', q: historySearch.trim(), include_svg: 'false' });
		if (historyManagerView === 'trash') params.set('trashed', 'true');
		if (historyManagerStarredOnly) params.set('starred', 'true');
		if (historyManagerForRevisionOnly) params.set('for_revision', 'true');
		if (historyManagerForShareOnly) params.set('for_share', 'true');
		try {
			const response = await apiFetch('/api/history/lineage-groups/' + encodeURIComponent(rootNodeId) + '/items?' + params.toString(), { cache: 'no-store', signal: controller.signal });
			if (!response.ok) throw new Error('HTTP ' + response.status);
			const data = await response.json() as { items: HistoryItem[] };
			if (active) lineageGroupItems = { ...lineageGroupItems, [rootNodeId]: data.items };
		} catch (error) {
			if (!(error instanceof DOMException && error.name === 'AbortError')) {
				lineageLoadFailed = true;
				lineageGroups = [];
				lineageGroupTotal = 0;
				lineageGroupItems = {};
				expandedRootIds = [];
				clearPreview();
			}
		} finally {
			lineageMemberLoadingIds = lineageMemberLoadingIds.filter((id) => id !== rootNodeId);
			if (lineageMemberControllers.get(rootNodeId) === controller) lineageMemberControllers.delete(rootNodeId);
		}
	}

	// Mirrors toggleLineageMemberStar: the parent owns the request, this keeps the
	// group's own copy of the member and its count in step.
	async function toggleLineageMemberForRevision(item: HistoryItem, event: MouseEvent): Promise<void> {
		event.preventDefault();
		event.stopPropagation();
		const nextForRevision = !item.for_revision;
		await onToggleForRevision(item, event);
		for (const [rootId, members] of Object.entries(lineageGroupItems)) {
			if (!members.some((member) => member.id === item.id)) continue;
			lineageGroupItems = { ...lineageGroupItems, [rootId]: members.map((member) => member.id === item.id ? { ...member, for_revision: nextForRevision } : member) };
			lineageGroups = lineageGroups.map((group) => group.root_node_id === rootId ? { ...group, for_revision_count: Math.max(0, group.for_revision_count + (nextForRevision ? 1 : -1)), representative: group.representative.id === item.id ? { ...group.representative, for_revision: nextForRevision } : group.representative } : group);
		}
	}

	async function toggleLineageMemberStar(item: HistoryItem, event: MouseEvent): Promise<void> {
		event.preventDefault();
		event.stopPropagation();
		const nextStarred = !item.starred;
		await onToggleStar(item, event);
		for (const [rootId, members] of Object.entries(lineageGroupItems)) {
			if (!members.some((member) => member.id === item.id)) continue;
			lineageGroupItems = { ...lineageGroupItems, [rootId]: members.map((member) => member.id === item.id ? { ...member, starred: nextStarred } : member) };
			lineageGroups = lineageGroups.map((group) => group.root_node_id === rootId ? { ...group, starred_count: Math.max(0, group.starred_count + (nextStarred ? 1 : -1)), representative: group.representative.id === item.id ? { ...group.representative, starred: nextStarred } : group.representative } : group);
		}
	}

	function setLineageGroupPage(page: number): void {
		lineageGroupPage = Math.max(0, Math.min(page, lineageGroupTotalPages - 1));
	}

	function selectLineageGroup(rootNodeId: string): void {
		for (const item of lineageGroupItems[rootNodeId] ?? []) {
			if (item.id && !selectedHistoryIds.includes(item.id)) toggleSelection(item);
		}
	}

	async function openPreview(item: HistoryItem): Promise<void> {
		if (!active || historyManagerView !== 'active' || !item.id) return;
		previewReturnElement = document.activeElement instanceof HTMLElement ? document.activeElement : null;
		const requestId = ++previewRequestId;
		previewController?.abort();
		const controller = new AbortController();
		previewController = controller;
		previewItem = item;
		previewLoading = true;
		previewError = false;
		try {
			// The listing intentionally omits SVG text. Read it only for this one,
			// explicitly selected preview; a list page never causes a full-SVG read.
			const response = await apiFetch(`/api/history/${encodeURIComponent(item.id)}/svg`, {
				cache: 'no-store', signal: controller.signal
			});
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const svg = await response.text();
			if (!active || requestId !== previewRequestId) return;
			previewItem = { ...item, svg };
		} catch (error) {
			if (requestId === previewRequestId && !(error instanceof DOMException && error.name === 'AbortError')) previewError = true;
		} finally {
			if (requestId === previewRequestId) previewLoading = false;
			if (previewController === controller) previewController = null;
		}
	}

	function clearPreview(restoreFocus = false): void {
		previewRequestId += 1;
		previewController?.abort();
		previewController = null;
		previewItem = null;
		previewLoading = false;
		previewError = false;
		if (restoreFocus) {
			const returnElement = previewReturnElement;
			requestAnimationFrame(() => returnElement?.isConnected && returnElement.focus());
		}
		previewReturnElement = null;
	}

	function previewArtwork(): void {
		if (previewReady && previewItem) onOpenArtwork(previewItem);
	}

	function activatePreviewArtwork(event: MouseEvent): void {
		// Keyboard activation and touch use one press; a mouse uses a double-click.
		if (event.detail === 0 || ('pointerType' in event && event.pointerType === 'touch')) previewArtwork();
	}

	function previewLineage(): void {
		if (previewReady && previewItem) onOpenLineage(previewItem);
	}

	function previewRefine(): void {
		if (previewReady && previewItem) onRefine(previewItem);
	}

	function handleThumbKeydown(event: KeyboardEvent, item: HistoryItem) {
		if (event.key !== 'Enter' && event.key !== ' ') return;
		event.preventDefault();
		void openPreview(item);
	}

	async function copyHash(item: HistoryItem, event: MouseEvent): Promise<void> {
		event.stopPropagation();
		event.preventDefault();
		const hash = item.render_hash;
		if (!hash) return;
		try {
			if (navigator.clipboard?.writeText) await navigator.clipboard.writeText(hash);
			else fallbackCopy(hash);
			copiedHistoryHash = hash;
			if (copiedHistoryHashTimer !== null) window.clearTimeout(copiedHistoryHashTimer);
			copiedHistoryHashTimer = window.setTimeout(() => {
				if (copiedHistoryHash === hash) copiedHistoryHash = null;
				copiedHistoryHashTimer = null;
			}, 1200);
		} catch {
			copiedHistoryHash = null;
		}
	}

	function fallbackCopy(text: string) {
		const textarea = document.createElement('textarea');
		textarea.value = text;
		textarea.setAttribute('readonly', '');
		textarea.style.position = 'fixed';
		textarea.style.left = '-9999px';
		textarea.style.top = '0';
		document.body.appendChild(textarea);
		textarea.select();
		try {
			document.execCommand('copy');
		} finally {
			document.body.removeChild(textarea);
		}
	}

	function thumbnailPromptText(text: string): string {
		return historyPreviewText(text.replace(/^\s*#\d+\s*/, ''));
	}

	function toggleStarFromThumb(item: HistoryItem, event: MouseEvent) {
		event.preventDefault();
		event.stopPropagation();
		void onToggleStar(item, event);
	}

	// The canonical page size: measured from the real grid, so this is the number
	// one page of the manager holds. The page's estimatedHistoryManagerPageSize()
	// is only a prediction for the first fetch made before the manager opens.
	// minCardWidth mirrors the minmax() in the .history-thumb-grid rule below and
	// must move whenever the CSS does. Card metadata is variable-height, so the
	// painted cards, rather than a fixed chrome estimate, own the row height.
	function calculatePageSize(element: HTMLElement): number {
		const grid = element.querySelector('.history-thumb-grid');
		const elementStyle = getComputedStyle(element);
		const cssPixels = (value: string): number => Number.parseFloat(value) || 0;
		const width = grid instanceof HTMLElement
			? grid.clientWidth
			: Math.max(0, element.clientWidth - cssPixels(elementStyle.paddingLeft) - cssPixels(elementStyle.paddingRight));
		const height = Math.max(0, element.clientHeight - cssPixels(elementStyle.paddingTop) - cssPixels(elementStyle.paddingBottom));
		if (width <= 0 || height <= 0) return 1;
		const computed = grid ? getComputedStyle(grid) : null;
		const gap = computed ? Number.parseFloat(computed.rowGap || computed.gap || '8') || 8 : 8;
		const minCardWidth = 142;
		const cardHeights = grid instanceof HTMLElement
			? [...grid.querySelectorAll('.manager-thumb-wrap')]
				.filter((card): card is HTMLElement => card instanceof HTMLElement)
				.map((card) => card.getBoundingClientRect().height)
			: [];
		return historyGridPageSize({ width, height, gap, minCardWidth, cardHeights });
	}

	$effect(() => {
		if (!active || historyDisplayMode !== 'lineage') return;
		// historyManagerTab is a dependency because the thumbnail tab asks the
		// server for a different set (min_items=2) than the list tab does.
		historyManagerView; historySearch; historyManagerStarredOnly; historyManagerForRevisionOnly; historyManagerForShareOnly; lineageGroupPage; managedHistoryTotal; trashTotal; historyManagerTab;
		void fetchLineageGroups();
	});

	$effect(() => {
		const element = thumbGridWrapEl;
		if (!active || !element || historyManagerTab !== 'thumbs' || historyDisplayMode !== 'chronological') return;
		let frame = 0;
		let debounceTimeout = 0;
		let pageSizeCeiling = 100;
		let viewportWidth = -1;
		let viewportHeight = -1;
		let lastReportedPageSize = 0;
		const reportPageSize = () => {
			const viewport = element.getBoundingClientRect();
			const nextViewportWidth = Math.round(viewport.width * 2) / 2;
			const nextViewportHeight = Math.round(viewport.height * 2) / 2;
			if (nextViewportWidth !== viewportWidth || nextViewportHeight !== viewportHeight) {
				viewportWidth = nextViewportWidth;
				viewportHeight = nextViewportHeight;
				pageSizeCeiling = 100;
			}
			// Changing the page changes which cards can be measured. Within one
			// viewport, only shrink the capacity so different card content cannot
			// make the manager alternate between two page sizes.
			pageSizeCeiling = Math.min(pageSizeCeiling, calculatePageSize(element));
			if (pageSizeCeiling === lastReportedPageSize) return;
			lastReportedPageSize = pageSizeCeiling;
			onSetPageSize(pageSizeCeiling);
		};
		const update = () => {
			cancelAnimationFrame(frame);
			clearTimeout(debounceTimeout);
			debounceTimeout = window.setTimeout(() => {
				frame = requestAnimationFrame(reportPageSize);
			}, 200);
		};
		// Initial calculation runs synchronously to avoid empty display flash
		reportPageSize();

		const observer = new ResizeObserver(update);
		observer.observe(element);
		const grid = element.querySelector('.history-thumb-grid');
		if (grid) observer.observe(grid);
		return () => {
			cancelAnimationFrame(frame);
			clearTimeout(debounceTimeout);
			observer.disconnect();
		};
	});

	$effect(() => {
		if (!historyManagerLoadFailed) return;
		clearPreview();
	});

	$effect(() => {
		const remembered = untrack(() => previewItem);
		if (active) {
			if (remembered?.id) void untrack(() => openPreview(remembered));
			return;
		}
		previewController?.abort();
		previewController = null;
		untrack(() => { previewRequestId += 1; });
		previewLoading = false;
		// Remember the target across visits, but read its authorized SVG again.
		if (remembered) previewItem = { ...remembered, svg: '' };
		lineageGroupController?.abort();
		for (const controller of lineageMemberControllers.values()) controller.abort();
	});
</script>

{#snippet shareStatus(item: HistoryItem)}
	{#if item.shared || hasAclShares(item) || isGroupShared(item)}
		<span class="share-statuses">
			{#if item.shared}<span class="share-status" title={isJapanese ? '他の利用者が所有する作品' : 'Owned by another member'}>{isJapanese ? '他の人の作品' : 'Another member’s work'}</span>{/if}
			{#if hasAclShares(item)}<span class="share-status" title={isJapanese ? '利用者またはグループに個別の権限を設定済み' : 'Individual access grants are set'}>{isJapanese ? '個別共有中' : 'Shared with guests'}</span>{/if}
			{#if isGroupShared(item)}<span class="share-status" title={isJapanese ? '共有先グループへの閲覧を許可中' : 'Group reading is enabled'}>{isJapanese ? 'グループ共有中' : 'Shared with group'}</span>{/if}
		</span>
	{/if}
{/snippet}

<section class="history-library" class:library-hidden={!active} aria-label={t().historyLibraryTitle} aria-hidden={!active} inert={!active} tabindex="-1">
	<div class="modal-head">
		<div class="history-head-left">
			<div class="catalog-modal-title">{t().historyLibraryTitle}</div>
			<div class="history-control-group">
				<span>{t().historyDisplayFormat}</span>
				<div class="settings-tabs history-mode-tabs">
				<Tooltip placement="bottom-right" text={t().tooltipHistoryThumbsTab}>
					<button class:active={historyManagerTab === 'thumbs'} onclick={() => selectHistoryManagerTab('thumbs')}>{t().historyThumbsTab}</button>
				</Tooltip>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryListTab}>
					<button class:active={historyManagerTab === 'list'} onclick={() => selectHistoryManagerTab('list')}>{t().historyListTab}</button>
				</Tooltip>
				</div>
			</div>
			<div class="history-control-group">
				<span>{t().historyGrouping}</span>
				<div class="settings-tabs history-group-tabs">
				<Tooltip placement="bottom-right" text={t().tooltipHistoryChronological}>
					<button class:active={historyDisplayMode === 'chronological'} onclick={() => setHistoryDisplayMode('chronological')}>{t().historyChronologicalMode}</button>
				</Tooltip>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryLineageGrouped}>
					<button class:active={historyDisplayMode === 'lineage'} onclick={() => setHistoryDisplayMode('lineage')}>{t().historyLineageMode}</button>
				</Tooltip>
				</div>
			</div>
			<span class="history-manager-count">
				{#if historyDisplayMode === 'lineage'}
					{groupDigits(lineageGroupTotal)} {t().historyLineageGroups}
					<!-- The thumbnail tab lists only lineages that have a derivation
					     (min_items=2); without saying so, every single work seemed gone. -->
					{#if lineageThumbsMode}{t().historyLineageGroupsDerivedOnly}{/if}
				{:else if managedHistoryTotal === 0}
					0 / 0
				{:else}
					{groupDigits(historyManagerOffset + 1)}-{groupDigits(historyManagerShownTo)} / {groupDigits(managedHistoryTotal)}
				{/if}
			</span>
		</div>
		<div class="history-head-actions">
			<div class="history-manager-pager">
				{#if historyDisplayMode === 'lineage'}
					<Tooltip placement="bottom-left" text={t().tooltipHistoryLatestPage}>
						<button class="ghost-btn history-latest-btn" onclick={() => setLineageGroupPage(0)} disabled={lineageGroupPage <= 0 || lineageGroupLoading}>{t().historyLatest}</button>
					</Tooltip>
					<Tooltip placement="bottom-left" text={t().tooltipHistoryNewerPage}>
						<button class="ghost-btn history-nav-btn" onclick={() => setLineageGroupPage(lineageGroupPage - 1)} disabled={lineageGroupPage <= 0 || lineageGroupLoading}>{t().historyNewer}</button>
					</Tooltip>
					<span>{lineageGroupLoading ? t().historyLoading : (lineageGroupPage + 1) + ' / ' + lineageGroupTotalPages}</span>
					<Tooltip placement="bottom-left" text={t().tooltipHistoryOlderPage}>
						<button class="ghost-btn history-nav-btn" onclick={() => setLineageGroupPage(lineageGroupPage + 1)} disabled={lineageGroupPage >= lineageGroupTotalPages - 1 || lineageGroupLoading}>{t().historyOlder}</button>
					</Tooltip>
					<Tooltip placement="bottom-left" text={t().tooltipHistoryOldestPage}>
						<button class="ghost-btn history-latest-btn" onclick={() => setLineageGroupPage(lineageGroupTotalPages - 1)} disabled={lineageGroupPage >= lineageGroupTotalPages - 1 || lineageGroupLoading}>{t().historyOldest}</button>
					</Tooltip>
				{:else}
					<Tooltip placement="bottom-left" text={t().tooltipHistoryLatestPage}>
						<button class="ghost-btn history-latest-btn" onclick={onSetLatestPage} disabled={historyManagerPage <= 0 || historyManagerLoading}>{t().historyLatest}</button>
					</Tooltip>
					<Tooltip placement="bottom-left" text={t().tooltipHistoryNewerPage}>
						<button class="ghost-btn history-nav-btn" onclick={() => onSetPage(historyManagerPage - 1)} disabled={historyManagerPage <= 0 || historyManagerLoading}>{t().historyNewer}</button>
					</Tooltip>
					<span>{historyManagerLoading ? t().historyLoading : (historyManagerPage + 1) + ' / ' + historyManagerTotalPages}</span>
					<Tooltip placement="bottom-left" text={t().tooltipHistoryOlderPage}>
						<button class="ghost-btn history-nav-btn" onclick={() => onSetPage(historyManagerPage + 1)} disabled={historyManagerPage >= historyManagerTotalPages - 1 || historyManagerLoading}>{t().historyOlder}</button>
					</Tooltip>
					<Tooltip placement="bottom-left" text={t().tooltipHistoryOldestPage}>
						<button class="ghost-btn history-latest-btn" onclick={onSetFirstPage} disabled={historyManagerPage >= historyManagerTotalPages - 1 || historyManagerLoading}>{t().historyOldest}</button>
					</Tooltip>
				{/if}
			</div>
			<Tooltip placement="bottom-left" text={t().historyLibraryReturn}>
				<button class="ghost-btn history-return" type="button" onclick={onClose}>{t().historyLibraryReturn}</button>
			</Tooltip>
		</div>
	</div>
	<div class="history-tools">
		<div class="history-tool-group">
			<Tooltip placement="bottom-right" text={t().tooltipHistorySelectAll}>
				<button class="ghost-btn" onclick={selectAllVisible}>{t().historySelectAll}</button>
			</Tooltip>
			<div class="history-filter-group" role="group" aria-label={t().historyFilterLabel}>
				<span class="history-filter-label">{t().historyFilterLabel}</span>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryStarredOnly}>
					<button
						class="ghost-btn history-filter-btn"
						class:ghost-active={historyManagerStarredOnly}
						aria-pressed={historyManagerStarredOnly}
						onclick={() => onSetStarredOnly(!historyManagerStarredOnly)}
					><span class="history-filter-check" class:visible={historyManagerStarredOnly} aria-hidden="true">✓</span>{t().historyStarredOnly}</button>
				</Tooltip>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryForRevisionOnly}>
					<button
						class="ghost-btn history-filter-btn"
						class:ghost-active={historyManagerForRevisionOnly}
						aria-pressed={historyManagerForRevisionOnly}
						onclick={() => onSetForRevisionOnly(!historyManagerForRevisionOnly)}
					><span class="history-filter-check" class:visible={historyManagerForRevisionOnly} aria-hidden="true">✓</span>{t().historyForRevisionOnly}</button>
				</Tooltip>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryForShareOnly}>
					<button
						class="ghost-btn history-filter-btn"
						class:ghost-active={historyManagerForShareOnly}
						aria-pressed={historyManagerForShareOnly}
						onclick={() => onSetForShareOnly(!historyManagerForShareOnly)}
					><span class="history-filter-check" class:visible={historyManagerForShareOnly} aria-hidden="true">✓</span>{t().historyForShareOnly}</button>
				</Tooltip>
			</div>
			<Tooltip placement="bottom-right" text={t().tooltipHistoryTrashView}>
				<button
					class="ghost-btn"
					class:ghost-active={historyManagerView === 'trash'}
					onclick={() => onSetView(historyManagerView === 'trash' ? 'active' : 'trash')}
				>{t().historyTrashButton(trashTotal)}</button>
			</Tooltip>
			{#if historyManagerView === 'active'}
				<Tooltip placement="bottom-right" text={t().tooltipHistoryMoveToTrash}>
				<button
					class="ghost-btn bulk-trash"
					type="button"
					onclick={() => onAskTrash(selectedHistoryIds)}
					disabled={selectedHistoryIds.length === 0}
					aria-label={t().historyMoveToTrash}
				>
					<svg viewBox="2 2 20 20" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M6 6l1 15h10l1-15"></path><path d="M10 10v7"></path><path d="M14 10v7"></path></svg>
					{#if selectedHistoryIds.length > 0}<span>{selectedHistoryIds.length}</span>{/if}
				</button>
				</Tooltip>
			{:else}
				<Tooltip placement="bottom-right" text={t().tooltipHistoryRestoreSelected}>
					<button class="ghost-btn" onclick={() => onAskRestore(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyRestoreSelected}</button>
				</Tooltip>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryPermanentDelete}>
					<button class="danger-btn" onclick={() => onAskPermanentDelete(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyPermanentDelete}</button>
				</Tooltip>
			{/if}
			{#if historyManagerView === 'active'}
				<SavedWorkExportMenu
					scope={checkedExportScope}
					animationSettings={animationExportSettings}
					{pngTemplates}
					onDownloadSVG={onDownloadSavedWorkSVG}
					onDownloadPNG={onDownloadSavedWorkPNG}
					onDownloadCard={onDownloadSavedWorkCard}
					onDownloadDdl={onDownloadSavedWorkDdl}
					onDownloadAnimation={onDownloadSavedWorkAnimation}
					onDownloadContactSheet={onDownloadSavedWorkContactSheet}
					onValidateSnapshot={onValidateSavedWorkExport}
				/>
			{/if}
		</div>
		<label class="history-search">{t().historySearchLabel} <input bind:value={historySearch} /></label>
	</div>
	{#if selectedHistoryIds.length > 0}
		<div class="history-selection-status">{t().historySelectionCount(selectedHistoryIds.length)}</div>
	{/if}
	{#if selectionResetReason}
		<div class="history-selection-reset" role="status">{t().historySelectionCleared(selectionResetReason)}</div>
	{/if}
	<div class="history-content" class:has-preview={!!previewItem || previewLoading}>
	{#if previewItem || previewLoading}
		<aside class="history-preview" aria-label={t().historyPreviewTitle}>
			<div class="history-preview-head"><strong>{t().historyPreviewTitle}</strong><button class="ghost-btn" type="button" onclick={() => clearPreview(true)}>{t().closeLabel}</button></div>
			{#if previewLoading}<p>{t().historyPreviewLoading}</p>{/if}
			{#if previewError}<p>{t().historyPreviewUnavailable}</p>{/if}
			{#if previewItem && !previewLoading && !previewError}
				<button
					class="history-preview-art"
					type="button"
					aria-label={t().historyPreviewOpenArtwork}
					title={t().historyPreviewOpenHint}
					onclick={activatePreviewArtwork}
					ondblclick={previewArtwork}
				>
					<HistoryThumbnail item={previewItem} scope={'library-preview-' + previewItem.id} size="manager" />
				</button>
				<p class="history-preview-open-hint">{t().historyPreviewOpenHint}</p>
				<p class="history-preview-description">{previewItem.source_text ?? previewItem.input}</p>
				{@render shareStatus(previewItem)}
				<div class="history-preview-actions">
					{#if previewReady}
						<button class="ghost-btn" type="button" onclick={previewLineage}>{t().historyPreviewOpenLineage}</button>
						<button class="ghost-btn" type="button" onclick={previewRefine}>{t().historyPreviewRefine}</button>
						{#if onShareItem && previewItem && !previewItem.shared}<button class="ghost-btn" type="button" onclick={() => previewItem && onShareItem?.(previewItem)}>{isJapanese ? '共有設定' : 'Share settings'}</button>{/if}
						<SavedWorkExportMenu
							scope={previewExportScope}
							animationSettings={animationExportSettings}
							{pngTemplates}
							onDownloadSVG={onDownloadSavedWorkSVG}
							onDownloadPNG={onDownloadSavedWorkPNG}
							onDownloadCard={onDownloadSavedWorkCard}
							onDownloadDdl={onDownloadSavedWorkDdl}
							onDownloadAnimation={onDownloadSavedWorkAnimation}
							onDownloadContactSheet={onDownloadSavedWorkContactSheet}
							onValidateSnapshot={onValidateSavedWorkExport}
						/>
					{/if}
				</div>
				<section class="history-preview-details" aria-label={t().historyPreviewDetails}>
					<h3>{t().historyPreviewDetails}</h3>
					<dl>
						<div><dt>{t().historyCreatedAtHeader}</dt><dd>{formatHistoryMinute(previewItem.at, isJapanese ? 'ja-JP' : 'en-US')}</dd></div>
						{#each modelLines(previewItem) as model}
							<div><dt>{model.label ?? t().historyModelHeader}</dt><dd>{model.full}</dd></div>
						{/each}
						<div><dt>{t().historyCatalogHeader}</dt><dd>{catalogName(previewItem.catalog_id)}</dd></div>
						{#if previewItem.render_canvas_aspect_id || previewItem.render_canvas_aspect}
							<div><dt>{t().historyCanvasHeader}</dt><dd>{getCanvasAspectOption(previewItem.render_canvas_aspect_id ?? previewItem.render_canvas_aspect).label}</dd></div>
						{/if}
						{#if previewItem.elapsed_ms != null}
							<div><dt>{t().historySecondsHeader}</dt><dd>{groupDigits(previewItem.elapsed_ms / 1000, 1)} s</dd></div>
						{/if}
						<div><dt>{t().historySvgSizeHeader}</dt><dd>{formatByteSize(previewItem.svg_bytes)}</dd></div>
						<div><dt>{t().historyPreviewRenderVersion}</dt><dd>{previewItem.render_engine_version ?? t().historyVersionNotRecorded}</dd></div>
						{#if previewItem.lineage_generation}
							<div><dt>{t().historyStripFieldGeneration}</dt><dd>{groupDigits(previewItem.lineage_generation)}</dd></div>
						{/if}
						{#if previewItem.render_hash}
							<div>
								<dt>{t().historyHashHeader}</dt>
								<dd class="history-preview-hash">
									<span>#{(previewItem.render_hash_short ?? previewItem.render_hash.slice(-4)).toUpperCase()}</span>
									<button
										type="button"
										title={copiedHistoryHash === previewItem.render_hash ? t().historyHashCopied : t().historyHashCopyTitle}
										aria-label={t().historyHashCopyTitle}
										onclick={(event) => previewItem && copyHash(previewItem, event)}
									>
										<svg viewBox="0 0 20 20" width="14" height="14" fill="none" stroke="currentColor" stroke-width="1.5" aria-hidden="true"><rect x="7" y="7" width="10" height="10" rx="1.5"/><path d="M13 7V4.5A1.5 1.5 0 0 0 11.5 3h-7A1.5 1.5 0 0 0 3 4.5v7A1.5 1.5 0 0 0 4.5 13H7"/></svg>
									</button>
								</dd>
							</div>
						{/if}
						{#if previewItem.note}<div><dt>{t().selectionNoteLabel}</dt><dd>{previewItem.note}</dd></div>{/if}
					</dl>
				</section>
			{/if}
		</aside>
	{/if}
	{#if historyManagerLoadFailed}
		<div class="history-load-failure" role="alert">
			<p>{t().historyLibraryLoadFailed}</p>
			<button class="ghost-btn" type="button" onclick={onRetryLoad}>{t().historyLibraryRetry}</button>
		</div>
	{:else if historyDisplayMode === 'lineage'}
		<div class="lineage-history-list" class:list-mode={historyManagerTab === 'list'} class:thumbs-mode={lineageThumbsMode}>
			{#if lineageGroupLoading}
				<div class="lineage-history-message">{t().historyLoading}</div>
			{:else if lineageLoadFailed}
				<div class="history-load-failure" role="alert">
					<p>{t().historyLibraryLoadFailed}</p>
					<button class="ghost-btn" type="button" onclick={() => void fetchLineageGroups()}>{t().historyLibraryRetry}</button>
				</div>
			{:else if lineageGroups.length === 0}
				<div class="lineage-history-message">{t().historyLineageEmpty}</div>
			{:else}
				{#each lineageGroups as group (group.root_node_id)}
					<article class="lineage-history-group" class:current-lineage={currentLineageRootId === group.root_node_id}>
						<div class="lineage-group-head">
							{#if !lineageThumbsMode}
								<button class="lineage-representative" type="button" title={t().historyPreviewTitle} onclick={() => void openPreview(group.representative)}>
									<HistoryThumbnail item={group.representative} scope={'lineage-group-' + group.root_node_id} size="mini" />
								</button>
							{/if}
							<div class="lineage-group-summary">
								<!-- A work drawn straight from DDL has no description; its label ('DDL') is what the
								     thumbnail grid shows for it, so the group names it the same way. -->
								<strong>{thumbnailPromptText(group.representative.source_text ?? group.representative.input) || group.representative.display_label || ''}</strong>
								<span>{t().historyLineageWorkCount(group.item_count)} · {t().historyLineageStarCount(group.starred_count)} · {t().historyLineageForRevisionCount(group.for_revision_count)} · {formatHistoryDate(group.latest_at)}</span>
								{#if currentLineageRootId === group.root_node_id}<span class="current-lineage-badge">{t().historyCurrentLineage}</span>{/if}
							</div>
							{#if !lineageThumbsMode}
								<button class="ghost-btn" type="button" title={t().historyLineageExpandTitle} onclick={() => toggleLineageGroup(group.root_node_id)} aria-expanded={expandedRootIds.includes(group.root_node_id)}>
									{expandedRootIds.includes(group.root_node_id) ? t().historyLineageCollapse : t().historyLineageExpand}
								</button>
							{/if}
						</div>
						{#if lineageThumbsMode || expandedRootIds.includes(group.root_node_id)}
							<div class="lineage-group-tools"><button class="ghost-btn" type="button" title={t().historySelectLineageTitle} disabled={!lineageGroupItems[group.root_node_id]} onclick={() => selectLineageGroup(group.root_node_id)}>{t().historySelectLineage}</button></div>
							{#if lineageMemberLoadingIds.includes(group.root_node_id)}
								<div class="lineage-history-message">{t().historyLoading}</div>
							{:else}
								<div class="lineage-member-grid">
									{#each lineageThumbsMode ? lineageLaneItems(group) : membersInGenerationOrder(lineageGroupItems[group.root_node_id]) as it (it.id ?? it.at)}
										<div class="lineage-member" class:current-work={currentHistoryId === it.id} class:selected={!!it.id && selectedHistoryIds.includes(it.id)}>
											<button type="button" class="selection-checkbox" class:checked={!!it.id && selectedHistoryIds.includes(it.id)} title={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} aria-label={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} onclick={() => toggleSelection(it)}><span aria-hidden="true">{it.id && selectedHistoryIds.includes(it.id) ? '✓' : ''}</span></button>
											{#if lineageThumbsMode && it.lineage_generation != null}<span class="lineage-generation-badge" title={t().historyGenerationTitle}>{it.lineage_generation}</span>{/if}
											<div class="lineage-member-content">
												<button class="lineage-member-main" type="button" title={t().historyPreviewTitle} onclick={() => void openPreview(it)}>
													<HistoryThumbnail item={it} scope={'lineage-member-' + it.id} size={historyManagerTab === 'list' ? 'mini' : 'manager'} />
													<span>{thumbnailPromptText(it.source_text ?? it.input)}</span>
												</button>
												{@render shareStatus(it)}
											</div>
											<div class="lineage-member-actions">
												<button class="hash-row-star" class:starred={!!it.starred} title={it.starred ? t().starOn : t().starOff} aria-label={it.starred ? t().starOn : t().starOff} onclick={(event) => toggleLineageMemberStar(it, event)}>★</button>
												<button class="hash-row-mark" class:marked={!!it.for_revision} title={it.for_revision ? t().forRevisionOn : t().forRevisionOff} aria-label={it.for_revision ? t().forRevisionOn : t().forRevisionOff} onclick={(event) => toggleLineageMemberForRevision(it, event)}>⚑</button>
												{#if historyManagerView === 'active'}
													{#if onShareItem && !it.shared}<button class="ghost-btn" type="button" onclick={() => onShareItem?.(it)}>{isJapanese ? '共有設定' : 'Share settings'}</button>{/if}
													<button class="ghost-btn icon-trash-btn" title={t().historyTrashItemTitle} onclick={() => it.id && onAskTrash([it.id])} aria-label={t().deleteButton}>⌫</button>
												{:else}
													<button class="ghost-btn" title={t().historyRestoreTitle} onclick={() => it.id && onAskRestore([it.id])}>{t().historyRestore}</button>
													<button class="danger-btn" title={t().historyPermanentDeleteTitle} onclick={() => it.id && onAskPermanentDelete([it.id])}>{t().historyPermanentDelete}</button>
												{/if}
											</div>
										</div>
									{/each}
								</div>
							{/if}
						{/if}
					</article>
				{/each}
			{/if}
		</div>
	{:else if !historyManagerLoading && managedHistoryItems.length === 0}
		<!-- An empty page said nothing at all; an emptied trash looked unloaded. -->
		<div class="history-empty-message">{historyManagerView === 'trash' ? t().historyTrashEmpty : t().historyLibraryEmpty}</div>
	{:else if historyManagerTab === 'thumbs'}
		<div class="history-thumb-grid-wrap" bind:this={thumbGridWrapEl}>
			<div class="history-thumb-grid">
				{#each managedHistoryItems as it (it.id ?? it.at)}
					<div class="manager-thumb-wrap" class:selected={!!it.id && selectedHistoryIds.includes(it.id)}>
<button
	type="button"
	class="manager-check selection-checkbox"
	class:checked={!!it.id && selectedHistoryIds.includes(it.id)}
	title={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))}
	role="checkbox"
	aria-checked={!!it.id && selectedHistoryIds.includes(it.id)}
	aria-label={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))}
	onclick={(event) => { event.stopPropagation(); toggleSelection(it); }}
><span aria-hidden="true">{it.id && selectedHistoryIds.includes(it.id) ? '✓' : ''}</span></button>
						{#if it.lineage_generation}
							<span class="manager-generation" title={t().historyGenerationTitle}>{it.lineage_generation}</span>
						{/if}
						<div
							class="thumb manager-thumb"
							title={t().historyPreviewTitle}
							onclick={() => void openPreview(it)}
							onkeydown={(event) => handleThumbKeydown(event, it)}
							role="button"
							tabindex={historyManagerView === 'active' ? 0 : -1}
						>
							<HistoryThumbnail item={it} scope="manager" size="manager" />
						</div>
						<div class="manager-thumb-actions">
							{#if it.display_label}<span class="history-display-label">{it.display_label}</span>{/if}
							<HistoryDescription text={historyListDescription(it.source_text ?? it.input)} className="thumb-description" />
							{@render shareStatus(it)}
							{#if it.note}<div class="thumb-note"><span>{t().selectionNoteLabel}</span>{it.note}</div>{/if}
							<div class="thumb-action-row">
								<button
									class="hash-row-star"
									class:starred={!!it.starred}
									onclick={(event) => toggleStarFromThumb(it, event)}
									title={it.starred ? t().starOn : t().starOff}
									aria-label={it.starred ? t().starOn : t().starOff}
								>★</button>
								<button
									class="hash-row-mark"
									class:marked={!!it.for_revision}
									onclick={(event) => onToggleForRevision(it, event)}
									title={it.for_revision ? t().forRevisionOn : t().forRevisionOff}
									aria-label={it.for_revision ? t().forRevisionOn : t().forRevisionOff}
								>⚑</button>
								{#if it.render_hash}
									<Tooltip placement="top" text={copiedHistoryHash === it.render_hash ? t().historyHashCopied : t().historyHashCopyTitle}>
										<button type="button" class="hash-chip hash-icon" class:marked={copiedHistoryHash === it.render_hash} onclick={(event) => copyHash(it, event)} aria-label={t().historyHashCopyTitle}>#</button>
									</Tooltip>
								{/if}
								<div class="thumb-model">
									{#each modelLines(it) as model}
										<details class="history-model-detail">
											<summary>{#if model.label}<span class="model-role">{model.label}:</span>{/if}{model.compact}</summary>
											<span>{model.full}</span>
										</details>
									{/each}
								</div>
							</div>
							{#if historyManagerView === 'active' && onShareItem && !it.shared}<button class="ghost-btn share-settings-btn" type="button" onclick={() => onShareItem?.(it)}>{isJapanese ? '共有設定' : 'Share settings'}</button>{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}
		<div class="history-table-wrap">
			<table class="history-table">
				<colgroup>
					<col class="history-table-select" /><col class="history-table-image" /><col class="history-table-description" /><col class="history-table-created" /><col class="history-table-model" /><col class="history-table-catalog" /><col class="history-table-size" /><col class="history-table-hash" /><col class="history-table-actions" />
				</colgroup>
				<thead>
					<tr><th></th><th>{t().historyImageHeader}</th><th>{t().historyDescriptionHeader}</th><th>{t().historyCreatedAtHeader}</th><th>{t().historyModelHeader}</th><th>{t().historyCatalogHeader}</th><th>{t().historySvgSizeHeader}</th><th>{t().historyHashHeader}</th><th>{t().historyActionHeader}</th></tr>
				</thead>
				<tbody>
					{#each managedHistoryItems as it (it.id ?? it.at)}
						<tr>
							<td><button type="button" class="selection-checkbox table-check" class:checked={!!it.id && selectedHistoryIds.includes(it.id)} title={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} role="checkbox" aria-checked={!!it.id && selectedHistoryIds.includes(it.id)} aria-label={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} onclick={(event) => { event.stopPropagation(); toggleSelection(it); }}><span aria-hidden="true">{it.id && selectedHistoryIds.includes(it.id) ? '✓' : ''}</span></button></td>
							<td class="table-thumb-cell">
								<button
									class="table-thumb-select"
								onclick={() => void openPreview(it)}
									disabled={historyManagerView !== 'active'}
									title={t().historyPreviewTitle}
									aria-label={t().historyPreviewTitle}
								>
									<HistoryThumbnail item={it} scope="table" size="mini" />
								</button>
								<button
									class="thumb-star mini-star"
									class:starred={!!it.starred}
									onclick={(event) => onToggleStar(it, event)}
									title={it.starred ? t().starOn : t().starOff}
									aria-label={it.starred ? t().starOn : t().starOff}
								>★</button>
							</td>
							<td class="table-description"><HistoryDescription text={historyListDescription(it.source_text ?? it.input)} />{@render shareStatus(it)}</td>
							<td>{formatHistoryMinute(it.at, isJapanese ? 'ja-JP' : 'en-US')}</td>
							<td class="table-model">
								{#each modelLines(it) as model}
									<details class="history-model-detail">
										<summary>{#if model.label}<span class="model-role">{model.label}:</span>{/if}{model.compact}</summary>
										<span>{model.full}</span>
									</details>
								{/each}
							</td>
							<td>{catalogName(it.catalog_id)}</td>
							<td class="table-svg-size">{formatByteSize(it.svg_bytes)}</td>
							<td>
								{#if it.render_hash}
									<Tooltip placement="top" text={copiedHistoryHash === it.render_hash ? t().historyHashCopied : t().historyHashCopyTitle}>
										<button type="button" class="hash-chip hash-icon table-hash" class:marked={copiedHistoryHash === it.render_hash} onclick={(event) => copyHash(it, event)} aria-label={t().historyHashCopyTitle}>#</button>
									</Tooltip>
								{/if}
							</td>
							<td class="table-actions">
								<button
									class="hash-row-mark"
									class:marked={!!it.for_revision}
									onclick={(event) => onToggleForRevision(it, event)}
									title={it.for_revision ? t().forRevisionOn : t().forRevisionOff}
									aria-label={it.for_revision ? t().forRevisionOn : t().forRevisionOff}
								>⚑</button>
								{#if historyManagerView === 'active' && onShareItem && !it.shared}
									<button class="ghost-btn" onclick={() => onShareItem?.(it)} title={isJapanese ? 'この作品の共有設定' : 'Share settings for this work'}>{isJapanese ? '共有設定' : 'Share settings'}</button>
								{/if}
								{#if historyManagerView === 'active'}
									<button class="ghost-btn icon-trash-btn" onclick={() => it.id && onAskTrash([it.id])} title={t().historyTrashItemTitle} aria-label={t().deleteButton}>
										<svg viewBox="2 2 20 20" aria-hidden="true">
											<path d="M3 6h18" />
											<path d="M8 6V4h8v2" />
											<path d="M6 6l1 15h10l1-15" />
											<path d="M10 10v7" />
											<path d="M14 10v7" />
										</svg>
									</button>
								{:else}
									<button class="ghost-btn" title={t().historyRestoreTitle} onclick={() => it.id && onAskRestore([it.id])}>{t().historyRestore}</button>
									<button class="danger-btn" title={t().historyPermanentDeleteTitle} onclick={() => it.id && onAskPermanentDelete([it.id])}>{t().historyPermanentDelete}</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
	</div>
</section>

<style>
	.share-statuses { display: flex; flex-wrap: wrap; gap: 3px; margin-top: 3px; }
	.share-status {
		display: inline-block;
		padding: 0 0.35em;
		border: 1px solid var(--accent);
		border-radius: var(--btn-sm-radius);
		color: var(--accent);
		font-size: 0.75em;
		line-height: 1.35;
	}
	.share-settings-btn { align-self: flex-start; font-size: var(--btn-sm-font-size); }

	.lineage-history-list { min-height: 0; overflow: auto; padding: 10px 12px 16px; display: flex; flex-direction: column; gap: 10px; }
	.lineage-history-message, .history-empty-message { margin: auto; padding: 30px; color: var(--fg3); text-align: center; }
	.history-load-failure { margin: auto; display: grid; justify-items: center; gap: 10px; padding: 30px; color: var(--fg2); text-align: center; }
	.history-load-failure p { margin: 0; }
	.history-content { min-height: 0; flex: 1; display: grid; grid-template-columns: minmax(0, 1fr); }
	.history-content.has-preview { grid-template-columns: minmax(0, 1fr) minmax(280px, 360px); }
	.lineage-history-list, .history-thumb-grid-wrap, .history-table-wrap, .history-load-failure, .history-empty-message { order: 1; min-width: 0; }
	.lineage-history-group { flex: 0 0 auto; border: 1px solid var(--border); border-radius: var(--r-lg); background: var(--panel); overflow: hidden; }
	.lineage-history-group.current-lineage { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-light); }
	.lineage-group-head { display: flex; align-items: center; gap: 10px; padding: 9px 10px; background: var(--panel); }
	.lineage-representative { flex: 0 0 56px; width: 56px; height: 56px; padding: 0; border: 0; border-radius: var(--r); overflow: hidden; background: var(--bg); cursor: pointer; }
	.lineage-representative :global(svg) { width: 100%; height: 100%; }
	.lineage-group-summary { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
	.lineage-group-summary strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: var(--ui-font-size-12); font-weight: 600; }
	.lineage-group-summary > span { color: var(--fg3); font-size: var(--ui-font-size-10); }
	.current-lineage-badge { align-self: flex-start; padding: 2px 6px; border-radius: 999px; background: var(--accent-light); color: var(--accent) !important; }
	.lineage-group-tools { display: flex; justify-content: flex-end; padding: 6px 10px; border-top: 1px solid var(--border); background: var(--bg); }
	.lineage-member-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(132px, 1fr)); gap: 8px; padding: 8px 10px 12px; border-top: 1px solid var(--border); background: var(--bg); }
	.lineage-member { position: relative; min-width: 0; padding: 5px; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel); }
	.lineage-member.selected, .lineage-member.current-work { border-color: var(--accent); }
	.lineage-member > .selection-checkbox { position: absolute; top: 8px; left: 8px; z-index: 5; }
	.lineage-member-content { min-width: 0; }
	.lineage-member-main { width: 100%; min-width: 0; padding: 0; border: 0; background: transparent; color: var(--fg2); cursor: pointer; text-align: left; }
	.lineage-member-main :global(svg) { width: 100%; max-height: 110px; }
	.lineage-member-main span { display: block; overflow: hidden; margin-top: 4px; text-overflow: ellipsis; white-space: nowrap; font-size: var(--ui-font-size-10); }
	.lineage-member-actions { display: flex; flex-wrap: wrap; align-items: center; gap: 4px; margin-top: 5px; }
	.lineage-member-actions .ghost-btn, .lineage-member-actions .danger-btn { margin-left: 0; }
	.lineage-history-list.list-mode .lineage-member-grid { display: flex; flex-direction: column; }
	.lineage-history-list.list-mode .lineage-member { display: grid; grid-template-columns: 20px minmax(0, 1fr) auto; align-items: center; gap: 8px; }
	.lineage-history-list.list-mode .lineage-member > .selection-checkbox { position: static; }
	.lineage-history-list.list-mode .lineage-member-main { display: grid; grid-template-columns: 48px minmax(0, 1fr); align-items: center; gap: 8px; }
	.lineage-history-list.list-mode .lineage-member-main :global(svg) { width: 48px; height: 48px; }
	.lineage-history-list.list-mode .lineage-member-main span { margin-top: 0; }
	/* Thumbnail tab, lineage mode: the root begins one horizontal lane and its
	   descendants continue to the right in generation order. Horizontal overflow
	   preserves that relationship in narrow windows instead of wrapping a child
	   below an unrelated sibling. */
	.lineage-history-list.thumbs-mode .lineage-history-group { border-left: 3px solid var(--border); }
	.lineage-history-list.thumbs-mode .lineage-history-group.current-lineage { border-left-color: var(--accent); }
	.lineage-history-list.thumbs-mode .lineage-member-grid {
		display: flex;
		overflow-x: auto;
		overscroll-behavior-x: contain;
		scroll-snap-type: x proximity;
		background: color-mix(in srgb, var(--accent) 5%, var(--bg));
	}
	.lineage-history-list.thumbs-mode .lineage-member { flex: 0 0 142px; scroll-snap-align: start; }
	.lineage-generation-badge {
		position: absolute; top: 8px; right: 8px; z-index: 5;
		min-width: 16px; padding: 1px 5px;
		border-radius: 999px;
		background: var(--accent-light); color: var(--accent);
		font-size: var(--ui-font-size-9); line-height: 1.5; text-align: center;
		font-variant-numeric: tabular-nums;
	}
	@media (max-width: 640px) {
		.lineage-history-list.thumbs-mode .lineage-group-head { flex-wrap: wrap; }
	}
	.history-group-tabs { flex-shrink: 0; }
	.history-library.library-hidden { display: none; }
	.history-library {
		position: fixed;
		inset: 0;
		z-index: 401;
		background: var(--panel2);
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.modal-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 9px 12px;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}
	.history-head-left,
	.history-head-actions,
	.history-tool-group {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.history-head-left { flex: 1 1 auto; }
	.history-head-actions { flex: 0 0 auto; }
	.history-control-group { display: flex; align-items: center; gap: 5px; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.catalog-modal-title {
		flex: 0 0 auto;
		font-size: var(--ui-font-size-15);
		font-weight: 300;
		letter-spacing: 0.05em;
	}
	.history-return { white-space: nowrap; }
	/* No overflow clipping here: the tabs carry Tooltip bubbles that must escape the box.
	   The rounded corners live on the end buttons instead. */
	.settings-tabs {
		display: flex;
		gap: 0;
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: var(--r);
	}
	.settings-tabs :global(.tooltip-wrap) { align-items: stretch; }
	.settings-tabs button {
		padding: var(--btn-sm-padding);
		border: none;
		background: none;
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
	}
	/* -1px keeps the fill inside the container's 1px border. */
	.settings-tabs :global(.tooltip-wrap:first-child button) {
		border-radius: calc(var(--btn-sm-radius) - 1px) 0 0 calc(var(--btn-sm-radius) - 1px);
	}
	.settings-tabs :global(.tooltip-wrap:last-child button) {
		border-radius: 0 calc(var(--btn-sm-radius) - 1px) calc(var(--btn-sm-radius) - 1px) 0;
	}
	.settings-tabs :global(.tooltip-wrap + .tooltip-wrap button) { border-left: 1px solid var(--border); }
	.settings-tabs button.active { color: var(--fg); background: var(--panel); font-weight: 500; }
	.history-tools {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		padding: 7px 12px;
		border-bottom: 1px solid var(--border);
		flex-wrap: wrap;
	}
	.history-filter-group {
		display: flex;
		align-items: center;
		gap: 4px;
		flex-wrap: wrap;
		padding-left: 10px;
		border-left: 1px solid var(--border);
	}
	.history-filter-label {
		color: var(--fg3);
		font-size: var(--ui-font-size-12);
		font-weight: 400;
	}
	.history-filter-btn {
		display: inline-flex;
		align-items: center;
		gap: 2px;
		padding: 4px 3px;
		background: color-mix(in srgb, var(--panel) 88%, var(--fg2));
		border-color: color-mix(in srgb, var(--border2) 70%, var(--fg2));
		color: var(--fg);
		font-weight: 400;
	}
	.history-filter-btn.ghost-active {
		background: var(--action-bg);
		color: var(--action-fg);
		border-color: var(--action-bg);
	}
	.history-filter-btn.ghost-active:hover:not(:disabled) {
		background: var(--action-hover);
		color: var(--action-fg);
		border-color: var(--action-hover);
	}
	.history-filter-btn:focus-visible {
		outline: 2px solid var(--accent);
		outline-offset: 2px;
	}
	.history-filter-check {
		display: inline-grid;
		inline-size: 1em;
		place-items: center;
		line-height: 1;
		font-weight: 700;
		visibility: hidden;
	}
	.history-filter-check.visible { visibility: visible; }
	.history-mode-tabs { flex-shrink: 0; }
	.history-manager-count {
		font-size: var(--ui-font-size-12);
		color: var(--fg2);
		font-variant-numeric: tabular-nums;
		margin-right: 2px;
	}
	.history-search {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--fg2);
		font-size: var(--ui-font-size-12);
	}
	.history-search input {
		width: min(240px, 30vw);
		flex: 1;
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: var(--ui-font-size-12);
		font-family: inherit;
	}
	.history-selection-status,
	.history-selection-reset {
		padding: 5px 12px;
		font-size: var(--ui-font-size-12);
		border-bottom: 1px solid var(--border);
	}
	.history-selection-status { color: var(--accent); }
	.history-selection-reset { color: var(--fg2); background: var(--bg); }
	.history-preview {
		order: 2;
		min-width: 0;
		overflow: auto;
		padding: 12px;
		border-left: 1px solid var(--border2);
		background: var(--panel2);
	}
	.history-preview-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 8px; }
	.history-preview-art { display: block; width: 100%; padding: 0; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: inherit; overflow: hidden; cursor: pointer; }
	.history-preview-art:hover { border-color: var(--accent); }
	.history-preview-art:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.history-preview-art :global(svg) { display: block; width: 100%; max-height: 240px; }
	.history-preview-open-hint { margin: 5px 0 0; color: var(--fg3); font-size: var(--ui-font-size-10); text-align: right; }
	.history-preview-description { white-space: pre-wrap; font-size: var(--ui-font-size-14); line-height: 1.55; }
	.history-preview-actions { display: flex; flex-wrap: wrap; gap: 6px; }
	.history-preview-details { margin-top: 16px; padding-top: 12px; border-top: 1px solid var(--border2); }
	.history-preview-details h3 { margin: 0 0 8px; font-size: var(--ui-font-size-12); font-weight: 600; }
	.history-preview-details dl { margin: 0; }
	.history-preview-details dl > div { display: grid; grid-template-columns: 94px minmax(0, 1fr); gap: 8px; padding: 5px 0; border-top: 1px solid var(--border); font-size: var(--ui-font-size-12); line-height: 1.4; }
	.history-preview-details dt { color: var(--fg3); }
	.history-preview-details dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
	.history-preview-hash { display: flex; align-items: center; gap: 8px; }
	.history-preview-hash button { display: inline-flex; align-items: center; justify-content: center; width: 24px; height: 24px; padding: 0; border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); background: var(--panel); color: var(--fg); cursor: pointer; }
	.history-manager-pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		color: var(--fg2);
		font-size: var(--ui-font-size-12);
		font-variant-numeric: tabular-nums;
	}
	.history-nav-btn { min-width: 74px; }
	.history-latest-btn { min-width: 54px; }
	.history-thumb-grid-wrap,
	.history-table-wrap {
		padding: 8px 10px 6px;
		min-height: 0;
	}
	.history-thumb-grid-wrap { overflow: auto; }
	.history-table-wrap { overflow: auto; }
	@media (max-width: 760px) {
		.history-content.has-preview { grid-template-columns: minmax(0, 1fr); grid-template-rows: minmax(0, 1fr) minmax(220px, 38%); }
		.history-preview { border-left: 0; border-top: 1px solid var(--border2); }
	}
	.history-thumb-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(142px, 1fr));
		gap: 8px;
		align-items: start;
	}
	.manager-thumb-wrap {
		position: relative;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		padding: 5px;
		transition: border-color 0.12s, box-shadow 0.12s;
		contain: layout paint;
	}
	.manager-thumb-wrap.selected {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-light);
	}
.manager-check {
	position: absolute;
	top: 6px;
	left: 6px;
	z-index: 30;
}
/* Sits directly under the 16px checkbox, over the thumbnail, so it needs the
   same plate treatment the star badge uses to stay readable on any image. */
.manager-generation {
	position: absolute;
	top: 30px;
	left: 6px;
	z-index: 30;
	box-sizing: border-box;
	min-width: 16px;
	height: 16px;
	padding: 0 3px;
	display: inline-grid;
	place-items: center;
	border: 1px solid var(--thumb-plate-border);
	border-radius: 3px;
	background: var(--thumb-plate-bg);
	color: var(--thumb-plate-fg-read);
	font: 600 var(--ui-font-size-10)/1 system-ui, sans-serif;
}
.selection-checkbox {
	box-sizing: border-box;
	width: 20px;
	height: 20px;
	display: inline-grid;
	place-items: center;
	margin: 0;
	padding: 0;
	border: 1px solid color-mix(in srgb, var(--fg) 32%, var(--border));
	border-radius: 3px;
	background: color-mix(in srgb, var(--panel) 92%, transparent);
	color: var(--accent-fg);
	cursor: pointer;
	font: 700 var(--ui-font-size-12)/1 system-ui, sans-serif;
	box-shadow: 0 1px 3px rgba(0,0,0,.16);
}
.selection-checkbox:hover { border-color: var(--accent); }
.selection-checkbox:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.selection-checkbox.checked { border-color: var(--accent); color: var(--accent); }
.table-check { position: static; box-shadow: none; }
	.thumb-star {
		position: absolute;
		top: 5px;
		right: 5px;
		z-index: 31;
		width: 22px;
		height: 22px;
		border: 1px solid var(--thumb-plate-border);
		border-radius: 50%;
		background: var(--thumb-plate-bg);
		color: var(--thumb-plate-fg);
		font-size: var(--ui-font-size-19);
		line-height: 1;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.thumb-star.starred { color: var(--star-fg); background: var(--star-bg); border-color: var(--star-border); }
	.table-thumb-cell { position: relative; width: 66px; }
	.table-thumb-select {
		display: block;
		width: 48px;
		height: 48px;
		padding: 0;
		border: 0;
		background: transparent;
		cursor: pointer;
	}
	.table-thumb-select:disabled { cursor: default; }
	.table-thumb-cell :global(svg) {
		contain: paint;
	}
	.table-thumb-cell .mini-star {
		top: 2px;
		right: 2px;
		width: 22px;
		height: 22px;
		font-size: var(--ui-font-size-19);
	}
	.thumb {
		flex-shrink: 0;
		width: 82px;
		border: 2px solid transparent;
		border-radius: var(--r);
		overflow: hidden;
		background: var(--panel);
		cursor: pointer;
		padding: 0;
		font-family: inherit;
		position: relative;
		transition: border-color 0.1s;
	}
	.thumb-note { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg3); font-size: var(--ui-font-size-10); line-height: 1.25; }
	.thumb-note span { margin-right: 4px; font-weight: 600; }
	.thumb-action-row {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-end;
		gap: 4px;
		justify-content: flex-start;
		min-width: 0;
		position: relative;
		z-index: 40;
		margin-top: auto;
	}
	.hash-row-star {
		flex: 0 0 auto;
		position: relative;
		z-index: 41;
		box-sizing: border-box;
		width: 24px;
		height: 24px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		background: var(--panel);
		color: var(--fg3);
		font-size: var(--btn-sm-font-size);
		line-height: 1;
		cursor: pointer;
		pointer-events: auto;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
	}
	/* Keep the revision flag aligned with the other work actions. */
	.hash-row-mark {
		box-sizing: border-box;
		width: 24px;
		height: 24px;
		padding: 0;
		border: 1px solid var(--border);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg3);
		font-size: var(--ui-font-size-18);
		line-height: 1;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.hash-row-mark.marked {
		border-color: color-mix(in srgb, var(--danger) 48%, var(--border2));
		background: color-mix(in srgb, var(--danger) 12%, var(--panel));
		color: var(--danger);
	}
	.hash-row-star.starred {
		color: var(--star-fg);
		background: var(--star-bg);
		border-color: var(--star-border);
	}
	:global(html[data-theme='dark']) .hash-row-star:not(.starred) {
		color: #b8c0cc;
		border-color: rgba(255,255,255,0.22);
		background: rgba(255,255,255,0.06);
	}
	.hash-chip {
		align-self: flex-end;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-family: inherit;
		font-size: var(--ui-font-size-10);
		line-height: 1;
		padding: 3px 7px;
		cursor: copy;
	}
	.hash-chip:hover {
		border-color: var(--accent);
		color: var(--fg);
	}
	.hash-chip.marked {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
	.hash-icon {
		width: 24px;
		height: 24px;
		padding: 0;
		align-items: center;
		justify-content: center;
		font-size: var(--ui-font-size-13);
		font-weight: 600;
	}
	.table-hash {
		font-size: var(--ui-font-size-11);
		white-space: nowrap;
		word-break: normal;
		overflow-wrap: normal;
	}
	/* Model roles use the card width; marking controls do not squeeze them. */
	.thumb-model {
		flex: 1 0 100%;
		order: -1;
		min-width: 0;
		color: var(--fg2);
		font-size: var(--ui-font-size-12);
		line-height: 1.5;
	}
	.thumb-model .history-model-detail summary { white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.thumb-model .history-model-detail > span { font-size: var(--ui-font-size-12); }
	.manager-thumb {
		width: 100%;
	}
	.manager-thumb-actions {
		display: flex;
		flex-direction: column;
		gap: 4px;
		min-height: 64px;
		height: auto;
		overflow: visible;
		margin-top: 5px;
		min-width: 0;
		position: relative;
		z-index: 40;
	}
	.history-table {
		width: 100%;
		table-layout: fixed;
		border-collapse: collapse;
		background: var(--panel);
		font-size: var(--ui-font-size-12);
	}
	.history-table th,
	.history-table td {
		border: 1px solid var(--border);
		padding: 7px 8px;
		text-align: left;
		vertical-align: middle;
	}
	.history-table th { color: var(--fg3); font-weight: 500; background: var(--bg); }
	.history-table-select { width: 32px; }
	.history-table-image { width: 66px; }
	.history-table-description { width: 34%; }
	.history-table-created { width: 116px; }
	.history-table-model { width: 17%; }
	.history-table-catalog { width: 10%; }
	.history-table-size { width: 74px; }
	.history-table-hash { width: 72px; min-width: 72px; }
	.history-table-actions { width: 142px; }
	.table-description { vertical-align: top !important; }
	.table-model { vertical-align: top !important; overflow-wrap: anywhere; }
	.history-model-detail + .history-model-detail { margin-top: 3px; }
	.history-model-detail summary { cursor: pointer; overflow-wrap: anywhere; }
	.history-model-detail > span { display: block; margin-top: 2px; color: var(--fg3); font-size: var(--ui-font-size-12); overflow-wrap: anywhere; }
	.model-role { margin-right: 3px; color: var(--fg2); white-space: nowrap; }
	:global(.history-description) { color: var(--fg2); font-size: var(--ui-font-size-14); line-height: 1.4; }
	.table-svg-size { text-align: right; white-space: nowrap; font-variant-numeric: tabular-nums; }
	.table-actions { white-space: nowrap; }
	/* --action-* is the theme-aware primary pair; var(--fg) with a hardcoded
	   white label collapses to white-on-white in the dark theme. */
	.bulk-trash { min-width: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
	.bulk-trash svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
	.bulk-trash:disabled { opacity: .4; cursor: default; }
	.icon-trash-btn {
		box-sizing: border-box;
		width: 24px;
		height: 24px;
		padding: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: var(--fg2);
	}
	.icon-trash-btn svg {
		width: 16px;
		height: 16px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.7;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.icon-trash-btn:hover { color: var(--fg); }
	.danger-btn {
		padding: var(--btn-sm-padding);
		border: none;
		border-radius: var(--btn-sm-radius);
		background: var(--danger-bg);
		color: var(--danger-fg);
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
		font-family: inherit;
	}
	.danger-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.history-display-label { margin-right: 5px; color: var(--fg3); font-weight: 600; }
</style>
