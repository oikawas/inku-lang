<script lang="ts">
	import Tooltip from './Tooltip.svelte';
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
	import { saveBlob } from '$lib/features/export/save-target';
	import HistoryThumbnail from '$lib/components/HistoryThumbnail.svelte';
	import { type SheetVariant } from '$lib/contactSheet';
	import { runContactSheet } from '$lib/features/contact-sheet/run';
	import { buildContactSheetNotes, type ContactSheetNoteEntry } from '$lib/contactSheetNotes';
	import { downloadAnimation, type AnimationExportSettings } from '$lib/animationExport';
	import { downloadCard, type CardExportSettings } from '$lib/cardExport';

	type HistoryItem = {
		// Set only when the work is somebody else's, reached through a group
		// scope or an explicit grant. Absent for one's own.
		shared?: boolean;
		id?: string;
		input: string;
		source_text?: string | null;
		display_label?: string | null;
		lineage_generation?: number | null;
		ddl: string | null;
		thinking?: string | null;
		score: { instructions: unknown[] };
		svg: string;
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
	note?: string | null;
	};

	type LineageHistoryGroup = { root_node_id: string; representative: HistoryItem; item_count: number; starred_count: number; for_revision_count: number; latest_at: number };
	type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

	type Props = {
		historyManagerView: 'active' | 'trash';
		historyManagerTab: 'thumbs' | 'list';
		historyManagerPage: number;
		historyManagerLoading: boolean;
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
		cardExportSettings: CardExportSettings;
		historySearch: string;
		historyManagerStarredOnly: boolean;
		historyManagerForRevisionOnly: boolean;
		onClose: () => void;
		onSetView: (view: 'active' | 'trash') => void;
		onSetPage: (page: number) => void;
		onSetLatestPage: () => void | Promise<void>;
		onSetFirstPage: () => void | Promise<void>;
		onSetPageSize: (pageSize: number) => void;
		onSetStarredOnly: (value: boolean) => void;
		onSetForRevisionOnly: (value: boolean) => void;
		onToggleForRevision: (item: HistoryItem, event?: Event) => void | Promise<void>;
		onSelectAll: () => void;
		onAskTrash: (ids: string[]) => void;
		onAskRestore: (ids: string[]) => void;
		onAskPermanentDelete: (ids: string[]) => void;
		onToggleSelection: (id: string) => void;
		onLoadItem: (item: HistoryItem) => void;
		onToggleStar: (item: HistoryItem, event?: Event) => void | Promise<void>;
		// Absent in single-user mode, where there is nobody to share with.
		onShareItem?: ((item: HistoryItem) => void) | null;
		isJapanese?: boolean;
		historyModelSummary: (item: HistoryItem) => string;
		formatHistoryDate: (at: number) => string;
		formatElapsed: (ms: number | null | undefined) => string;
		catalogName: (id: string | null | undefined) => string;
		historyPreviewText: (text: string) => string;
		shortModel: (model: string | null | undefined) => string;
		apiFetch: ApiFetch;
		currentHistoryId?: string | null;
		currentLineageRootId?: string | null;
	};

	let {
		historyManagerView,
		historyManagerTab = $bindable('thumbs'),
		historyManagerPage,
		historyManagerLoading,
		historyManagerTotalPages,
		historyManagerOffset,
		historyManagerShownTo,
		managedHistoryItems,
		managedHistoryTotal,
		trashTotal,
		selectedHistoryIds,
		animationExportSettings,
		cardExportSettings,
		historySearch = $bindable(''),
		historyManagerStarredOnly,
		historyManagerForRevisionOnly,
		onClose,
		onSetView,
		onSetPage,
		onSetLatestPage,
		onSetFirstPage,
		onSetPageSize,
		onSetStarredOnly,
		onSetForRevisionOnly,
		onToggleForRevision,
		onSelectAll,
		onAskTrash,
		onAskRestore,
		onAskPermanentDelete,
		onToggleSelection,
		onLoadItem,
		onToggleStar,
		onShareItem = null,
		isJapanese = false,
		historyModelSummary,
		formatHistoryDate,
		formatElapsed,
		catalogName,
		historyPreviewText,
		shortModel,
		apiFetch,
		currentHistoryId = null,
		currentLineageRootId = null
	}: Props = $props();

	let thumbGridWrapEl = $state<HTMLDivElement | null>(null);
	let historyDisplayMode = $state<'chronological' | 'lineage'>('chronological');
	let lineageGroups = $state<LineageHistoryGroup[]>([]);
	let lineageGroupTotal = $state(0);
	let lineageGroupPage = $state(0);
	let lineageGroupLoading = $state(false);
	let expandedRootIds = $state<string[]>([]);
	let lineageGroupItems = $state<Record<string, HistoryItem[]>>({});
	let lineageMemberLoadingIds = $state<string[]>([]);
	let lineageRequestId = 0;
	let lineageGroupController: AbortController | null = null;
	const lineageMemberControllers = new Map<string, AbortController>();
	const lineageGroupPageSize = 8;
	const lineageGroupTotalPages = $derived(Math.max(1, Math.ceil(lineageGroupTotal / lineageGroupPageSize)));

	onMount(() => {
		try {
			if (localStorage.getItem('inku-history-display-mode') === 'lineage') historyDisplayMode = 'lineage';
		} catch {}
		return () => {
			lineageGroupController?.abort();
			for (const controller of lineageMemberControllers.values()) controller.abort();
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

	async function fetchLineageGroups(): Promise<void> {
		const requestId = ++lineageRequestId;
		lineageGroupController?.abort();
		const controller = new AbortController();
		lineageGroupController = controller;
		lineageGroupLoading = true;
		const params = new URLSearchParams({ offset: String(lineageGroupPage * lineageGroupPageSize), limit: String(lineageGroupPageSize), q: historySearch.trim() });
		if (historyManagerView === 'trash') params.set('trashed', 'true');
		if (historyManagerStarredOnly) params.set('starred', 'true');
		if (historyManagerForRevisionOnly) params.set('for_revision', 'true');
		// The thumbnail tab lays a lineage's works out side by side, so a lineage
		// holding one work has nothing to lay out. The server drops them, because
		// dropping them here would leave short pages and a total that disagrees.
		if (lineageThumbsMode) params.set('min_items', '2');
		try {
			const response = await apiFetch('/api/history/lineage-groups?' + params.toString(), { cache: 'no-store', signal: controller.signal });
			if (!response.ok) throw new Error('HTTP ' + response.status);
			const data = await response.json() as { groups: LineageHistoryGroup[]; total: number };
			if (requestId !== lineageRequestId) return;
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
			if (!(error instanceof DOMException && error.name === 'AbortError')) throw error;
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
		if (lineageGroupItems[rootNodeId]) return;
		lineageMemberLoadingIds = [...lineageMemberLoadingIds, rootNodeId];
		lineageMemberControllers.get(rootNodeId)?.abort();
		const controller = new AbortController();
		lineageMemberControllers.set(rootNodeId, controller);
		const params = new URLSearchParams({ limit: '10000', q: historySearch.trim() });
		if (historyManagerView === 'trash') params.set('trashed', 'true');
		if (historyManagerStarredOnly) params.set('starred', 'true');
		if (historyManagerForRevisionOnly) params.set('for_revision', 'true');
		try {
			const response = await apiFetch('/api/history/lineage-groups/' + encodeURIComponent(rootNodeId) + '/items?' + params.toString(), { cache: 'no-store', signal: controller.signal });
			if (!response.ok) throw new Error('HTTP ' + response.status);
			const data = await response.json() as { items: HistoryItem[] };
			lineageGroupItems = { ...lineageGroupItems, [rootNodeId]: data.items };
		} catch (error) {
			if (!(error instanceof DOMException && error.name === 'AbortError')) throw error;
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
		const ids = (lineageGroupItems[rootNodeId] ?? []).flatMap((item) => item.id ? [item.id] : []);
		for (const id of ids) if (!selectedHistoryIds.includes(id)) onToggleSelection(id);
	}

	let contactSheetBusy = $state<SheetVariant | null>(null);
	let contactSheetError = $state<string | null>(null);
	let animationExportBusy = $state(false);
	let animationExportError = $state<string | null>(null);
	let cardExportBusy = $state(false);
	let cardExportError = $state<string | null>(null);

	// Selection can span pages. The current page and expanded lineage members are
	// checked first; off-page items are fetched on demand by export actions.
	/**
	 * The work, with its drawing.
	 *
	 * The listing asks for thumbnails rather than pictures, so the copy on the
	 * page carries an empty `svg`. Contact sheets and exports need the drawing
	 * itself, and an item without one is skipped in silence -- an empty sheet
	 * with no error. Falling through to the single-work fetch keeps that from
	 * being how it fails.
	 */
	async function resolveWorkWithSvg(id: string): Promise<HistoryItem | null> {
		const onPage = findSelectedItem(id);
		if (onPage?.svg) return onPage;
		return (await fetchHistoryItem(id)) ?? onPage;
	}

	function findSelectedItem(id: string): HistoryItem | null {
		const onPage = managedHistoryItems.find((it) => it.id === id);
		if (onPage) return onPage;
		for (const members of Object.values(lineageGroupItems)) {
			const member = members.find((it) => it.id === id);
			if (member) return member;
		}
		const representative = lineageGroups.find((group) => group.representative.id === id)?.representative;
		return representative ?? null;
	}

	async function fetchHistoryItem(id: string): Promise<HistoryItem | null> {
		try {
			const response = await apiFetch('/api/history/' + encodeURIComponent(id) + '/neighbors', { cache: 'no-store' });
			if (!response.ok) return null;
			const items = await response.json() as HistoryItem[];
			return items.find((it) => it.id === id) ?? null;
		} catch {
			return null;
		}
	}

	async function downloadSelectedAnimation(): Promise<void> {
		if (animationExportBusy || selectedHistoryIds.length < 2) return;
		animationExportBusy = true;
		animationExportError = null;
		try {
			const items: HistoryItem[] = [];
			for (const id of selectedHistoryIds) {
				const item = await resolveWorkWithSvg(id);
				if (item?.id) items.push(item);
			}
			if (items.length < 2) throw new Error("At least two saved works are required.");
			items.sort((left, right) => left.at - right.at || String(left.id).localeCompare(String(right.id)));
			await downloadAnimation(apiFetch, items.map((item) => item.id as string), animationExportSettings);
		} catch (cause) {
			const reason = cause instanceof Error ? cause.message : String(cause);
			animationExportError = t().animationExportFailed(reason);
		} finally {
			animationExportBusy = false;
		}
	}

	async function downloadSelectedCard(): Promise<void> {
		if (cardExportBusy || selectedHistoryIds.length !== 1) return;
		cardExportBusy = true;
		cardExportError = null;
		try {
			await downloadCard(apiFetch, selectedHistoryIds[0], cardExportSettings);
		} catch (cause) {
			const reason = cause instanceof Error ? cause.message : String(cause);
			cardExportError = t().cardExportFailed(reason);
		} finally {
			cardExportBusy = false;
		}
	}

	// The AI sheet carries index badges only, so the notes file has to restate
	// everything a caption would have said, plus the machinery behind the
	// performance. Labels stay English; the description keeps its own language.
	// Same single path as every other download -- see features/export/save-target.
	async function triggerDownload(blob: Blob, filename: string): Promise<void> {
		const outcome = await saveBlob(blob, filename, { enabled: downloadFolderSettings.enabled });
		if (outcome.kind === 'browser' && outcome.reason === 'denied') {
			contactSheetError = t().downloadFolderFellBack;
		}
	}

	async function downloadContactSheet(variant: SheetVariant): Promise<void> {
		if (contactSheetBusy || selectedHistoryIds.length === 0) return;
		contactSheetBusy = variant;
		contactSheetError = null;
		try {
			await runContactSheet(variant, {
				ids: () => selectedHistoryIds,
				resolveWork: (id) => resolveWorkWithSvg(id),
				catalogName,
				formatDate: formatHistoryDate,
				previewText: historyPreviewText,
				save: triggerDownload,
				labels: {
					title: t().historyContactSheetTitle,
					subtitle: (total, date, page, pages) => t().historyContactSheetSubtitle(total, date, page, pages),
				},
			});
		} catch {
			contactSheetError = t().historyContactSheetFailed;
		} finally {
			contactSheetBusy = null;
		}
	}

	function loadItemAndClose(item: HistoryItem) {
		if (historyManagerView !== 'active') return;
		onLoadItem(item);
		onClose();
	}

	function handleThumbKeydown(event: KeyboardEvent, item: HistoryItem) {
		if (event.key !== 'Enter' && event.key !== ' ') return;
		event.preventDefault();
		loadItemAndClose(item);
	}

	function hashLabel(item: HistoryItem): string {
		return (item.render_hash_short || item.render_hash?.slice(-4) || '').toUpperCase();
	}

	function copyHash(item: HistoryItem, event: MouseEvent) {
		event.stopPropagation();
		event.preventDefault();
		const hash = item.render_hash || hashLabel(item);
		if (!hash) return;
		if (navigator.clipboard?.writeText) {
			void navigator.clipboard.writeText(hash).catch(() => fallbackCopy(hash));
			return;
		}
		fallbackCopy(hash);
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
	// must move whenever the CSS does.
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
		const columns = Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)));
		// Derive the card height from the fixed CSS contract instead of measuring
		// rendered cards. Measuring content-visibility placeholders caused the
		// page size to alternate while thumbnails were being painted.
		const cardWidth = Math.max(minCardWidth, (width - gap * (columns - 1)) / columns);
		const cardChromeHeight = 75; // borders + padding + margin + 58px action area
		const imageWidth = Math.max(1, cardWidth - 12); // 5px padding and 1px border on both sides
		const cardHeight = imageWidth * 58 / 82 + cardChromeHeight;
		const rows = Math.max(1, Math.floor((height + gap) / (cardHeight + gap)));
		return Math.max(1, columns * rows);
	}

	$effect(() => {
		if (historyDisplayMode !== 'lineage') return;
		// historyManagerTab is a dependency because the thumbnail tab asks the
		// server for a different set (min_items=2) than the list tab does.
		historyManagerView; historySearch; historyManagerStarredOnly; historyManagerForRevisionOnly; lineageGroupPage; managedHistoryTotal; trashTotal; historyManagerTab;
		void fetchLineageGroups();
	});

	$effect(() => {
		const element = thumbGridWrapEl;
		if (!element || historyManagerTab !== 'thumbs' || historyDisplayMode !== 'chronological') return;
		let frame = 0;
		let debounceTimeout = 0;
		const update = () => {
			cancelAnimationFrame(frame);
			clearTimeout(debounceTimeout);
			debounceTimeout = window.setTimeout(() => {
				frame = requestAnimationFrame(() => onSetPageSize(calculatePageSize(element)));
			}, 200);
		};
		// Initial calculation runs synchronously to avoid empty display flash
		onSetPageSize(calculatePageSize(element));

		const observer = new ResizeObserver(update);
		observer.observe(element);
		return () => {
			cancelAnimationFrame(frame);
			clearTimeout(debounceTimeout);
			observer.disconnect();
		};
	});
</script>

<div class="modal-backdrop" onclick={onClose} aria-hidden="true"></div>
<div class="history-modal" role="dialog" aria-modal="true" tabindex="-1">
	<div class="modal-head">
		<div class="history-head-left">
			<div class="catalog-modal-title">{t().historyManagerTitle}</div>
			<div class="settings-tabs history-mode-tabs">
				<Tooltip placement="bottom-right" text={t().tooltipHistoryThumbsTab}>
					<button class:active={historyManagerTab === 'thumbs'} onclick={() => selectHistoryManagerTab('thumbs')}>{t().historyThumbsTab}</button>
				</Tooltip>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryListTab}>
					<button class:active={historyManagerTab === 'list'} onclick={() => selectHistoryManagerTab('list')}>{t().historyListTab}</button>
				</Tooltip>
			</div>
			<div class="settings-tabs history-group-tabs">
				<Tooltip placement="bottom-right" text={t().tooltipHistoryChronological}>
					<button class:active={historyDisplayMode === 'chronological'} onclick={() => setHistoryDisplayMode('chronological')}>{t().historyChronologicalMode}</button>
				</Tooltip>
				<Tooltip placement="bottom-right" text={t().tooltipHistoryLineageGrouped}>
					<button class:active={historyDisplayMode === 'lineage'} onclick={() => setHistoryDisplayMode('lineage')}>{t().historyLineageMode}</button>
				</Tooltip>
			</div>
			<span class="history-manager-count">
				{#if historyDisplayMode === 'lineage'}
					{lineageGroupTotal} {t().historyLineageGroups}
				{:else if managedHistoryTotal === 0}
					0 / 0
				{:else}
					{historyManagerOffset + 1}-{historyManagerShownTo} / {managedHistoryTotal}
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
			<Tooltip placement="bottom-left" text={t().tooltipHistoryClose}>
				<button class="catalog-close" onclick={onClose} aria-label={t().tooltipHistoryClose}>×</button>
			</Tooltip>
		</div>
	</div>
	<div class="history-tools">
		<div class="history-tool-group">
			<Tooltip placement="bottom-right" text={t().tooltipHistorySelectAll}>
				<button class="ghost-btn" onclick={onSelectAll}>{t().historySelectAll}</button>
			</Tooltip>
			<Tooltip placement="bottom-right" text={t().tooltipHistoryStarredOnly}>
				<button
					class="ghost-btn"
					class:ghost-active={historyManagerStarredOnly}
					onclick={() => onSetStarredOnly(!historyManagerStarredOnly)}
				>{t().historyStarredOnly}</button>
			</Tooltip>
			<Tooltip placement="bottom-right" text={t().tooltipHistoryForRevisionOnly}>
				<button
					class="ghost-btn"
					class:ghost-active={historyManagerForRevisionOnly}
					onclick={() => onSetForRevisionOnly(!historyManagerForRevisionOnly)}
				>{t().historyForRevisionOnly}</button>
			</Tooltip>
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
			<!-- The trash view restores or deletes; it does not produce work from a
			     work. The server refuses a trashed id on these routes (I-094), so
			     leaving the buttons here would only offer a 404. -->
			{#if historyManagerView === 'active'}
			<Tooltip placement="bottom-left" wide text={t().historyContactSheetHint}>
				<button
					class="ghost-btn"
					type="button"
					onclick={() => downloadContactSheet('review')}
					disabled={selectedHistoryIds.length === 0 || contactSheetBusy !== null}
				>
					{contactSheetBusy === 'review' ? t().historyContactSheetBusy : t().historyContactSheet}
					{#if contactSheetBusy === null && selectedHistoryIds.length > 0}<span class="tool-count">{selectedHistoryIds.length}</span>{/if}
				</button>
			</Tooltip>
			<Tooltip placement="bottom-left" wide text={t().historyContactSheetAiHint}>
				<button
					class="ghost-btn"
					type="button"
					onclick={() => downloadContactSheet('ai')}
					disabled={selectedHistoryIds.length === 0 || contactSheetBusy !== null}
				>
					{contactSheetBusy === 'ai' ? t().historyContactSheetBusy : t().historyContactSheetAi}
				</button>
			</Tooltip>
			<Tooltip placement="bottom-left" wide text={t().historyAnimationExportHint}>
				<button
					class="ghost-btn"
					type="button"
					onclick={downloadSelectedAnimation}
					disabled={selectedHistoryIds.length < 2 || animationExportBusy}
				>
					{animationExportBusy ? t().animationExportBusy : t().historyAnimationExport}
					{#if !animationExportBusy && selectedHistoryIds.length > 0}<span class="tool-count">{selectedHistoryIds.length}</span>{/if}
				</button>
			</Tooltip>
			<Tooltip placement="bottom-left" wide text={t().historyCardExportHint}>
				<button
					class="ghost-btn"
					type="button"
					onclick={downloadSelectedCard}
					disabled={selectedHistoryIds.length !== 1 || cardExportBusy}
				>
					{cardExportBusy ? t().cardExportBusy : t().historyCardExport}
				</button>
			</Tooltip>
			{#if animationExportError}<span class="tool-error">{animationExportError}</span>{/if}
			{#if cardExportError}<span class="tool-error">{cardExportError}</span>{/if}
			{#if contactSheetError}<span class="tool-error">{contactSheetError}</span>{/if}
			{/if}
		</div>
		<label class="history-search">{t().historySearchLabel} <input bind:value={historySearch} /></label>
	</div>
	{#if historyDisplayMode === 'lineage'}
		<div class="lineage-history-list" class:list-mode={historyManagerTab === 'list'} class:thumbs-mode={lineageThumbsMode}>
			{#if lineageGroupLoading}
				<div class="lineage-history-message">{t().historyLoading}</div>
			{:else if lineageGroups.length === 0}
				<div class="lineage-history-message">{t().historyLineageEmpty}</div>
			{:else}
				{#each lineageGroups as group (group.root_node_id)}
					<article class="lineage-history-group" class:current-lineage={currentLineageRootId === group.root_node_id}>
						<div class="lineage-group-head">
							<button class="lineage-representative" type="button" title={t().historyOpenItemTitle} onclick={() => loadItemAndClose(group.representative)}>
								<HistoryThumbnail item={group.representative} scope={'lineage-group-' + group.root_node_id} size="mini" />
							</button>
							<div class="lineage-group-summary">
								<strong>{thumbnailPromptText(group.representative.source_text ?? group.representative.input)}</strong>
								<span>{t().historyLineageWorkCount(group.item_count)} · {t().historyLineageStarCount(group.starred_count)} · {t().historyLineageForRevisionCount(group.for_revision_count)} · {formatHistoryDate(group.latest_at)}</span>
								{#if currentLineageRootId === group.root_node_id}<span class="current-lineage-badge">{t().historyCurrentLineage}</span>{/if}
							</div>
							<button class="ghost-btn" type="button" title={t().historyLineageExpandTitle} onclick={() => toggleLineageGroup(group.root_node_id)} aria-expanded={expandedRootIds.includes(group.root_node_id)}>
								{expandedRootIds.includes(group.root_node_id) ? t().historyLineageCollapse : t().historyLineageExpand}
							</button>
						</div>
						{#if expandedRootIds.includes(group.root_node_id)}
							<div class="lineage-group-tools"><button class="ghost-btn" type="button" title={t().historySelectLineageTitle} disabled={!lineageGroupItems[group.root_node_id]} onclick={() => selectLineageGroup(group.root_node_id)}>{t().historySelectLineage}</button></div>
							{#if lineageMemberLoadingIds.includes(group.root_node_id)}
								<div class="lineage-history-message">{t().historyLoading}</div>
							{:else}
								<div class="lineage-member-grid">
									{#each membersInGenerationOrder(lineageGroupItems[group.root_node_id]) as it (it.id ?? it.at)}
										<div class="lineage-member" class:current-work={currentHistoryId === it.id} class:selected={!!it.id && selectedHistoryIds.includes(it.id)}>
											<button type="button" class="selection-checkbox" class:checked={!!it.id && selectedHistoryIds.includes(it.id)} title={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} aria-label={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} onclick={() => it.id && onToggleSelection(it.id)}><span aria-hidden="true">{it.id && selectedHistoryIds.includes(it.id) ? '✓' : ''}</span></button>
											{#if lineageThumbsMode && it.lineage_generation != null}<span class="lineage-generation-badge" title={t().historyGenerationTitle}>{it.lineage_generation}</span>{/if}
											<button class="lineage-member-main" type="button" title={t().historyOpenItemTitle} onclick={() => loadItemAndClose(it)}>
												<HistoryThumbnail item={it} scope={'lineage-member-' + it.id} size={historyManagerTab === 'list' ? 'mini' : 'manager'} />
												<span>{thumbnailPromptText(it.source_text ?? it.input)}</span>
											</button>
											<div class="lineage-member-actions">
												<button class="hash-row-star" class:starred={!!it.starred} title={it.starred ? t().starOn : t().starOff} aria-label={it.starred ? t().starOn : t().starOff} onclick={(event) => toggleLineageMemberStar(it, event)}>★</button>
												<button class="hash-row-mark" class:marked={!!it.for_revision} title={it.for_revision ? t().forRevisionOn : t().forRevisionOff} aria-label={it.for_revision ? t().forRevisionOn : t().forRevisionOff} onclick={(event) => toggleLineageMemberForRevision(it, event)}>✎</button>
												{#if historyManagerView === 'active'}
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
	onclick={(event) => { event.stopPropagation(); if (it.id) onToggleSelection(it.id); }}
><span aria-hidden="true">{it.id && selectedHistoryIds.includes(it.id) ? '✓' : ''}</span></button>
						{#if it.lineage_generation}
							<span class="manager-generation" title={t().historyGenerationTitle}>{it.lineage_generation}</span>
						{/if}
						<div
							class="thumb manager-thumb"
							title={t().historyOpenItemTitle}
							onclick={() => loadItemAndClose(it)}
							onkeydown={(event) => handleThumbKeydown(event, it)}
							role="button"
							tabindex={historyManagerView === 'active' ? 0 : -1}
						>
							<HistoryThumbnail item={it} scope="manager" size="manager" />
						</div>
						<div class="manager-thumb-actions">
							<div class="thumb-catalog" title={it.source_text ?? it.input}>{#if it.display_label}<span class="history-display-label">{it.display_label}</span>{/if}<span>{thumbnailPromptText(it.source_text ?? it.input)}</span></div>
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
								>✎</button>
								{#if hashLabel(it)}<button class="hash-chip" onclick={(event) => copyHash(it, event)} title={t().historyHashCopyTitle}>{hashLabel(it)}</button>{/if}
								<span class="thumb-model" title={historyModelSummary(it)}>{historyModelSummary(it)}</span>
							</div>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}
		<div class="history-table-wrap">
			<table class="history-table">
				<thead>
					<tr><th></th><th>{t().historyImageHeader}</th><th>{t().historyHashHeader}</th><th>{t().historyCreatedAtHeader}</th><th>{t().historyModelHeader}</th><th>{t().historySecondsHeader}</th><th>{t().historyCatalogHeader}</th><th>{t().historyActionHeader}</th></tr>
				</thead>
				<tbody>
					{#each managedHistoryItems as it (it.id ?? it.at)}
						<tr>
							<td><button type="button" class="selection-checkbox table-check" class:checked={!!it.id && selectedHistoryIds.includes(it.id)} title={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} role="checkbox" aria-checked={!!it.id && selectedHistoryIds.includes(it.id)} aria-label={t().historySelectItem(!!it.id && selectedHistoryIds.includes(it.id))} onclick={(event) => { event.stopPropagation(); if (it.id) onToggleSelection(it.id); }}><span aria-hidden="true">{it.id && selectedHistoryIds.includes(it.id) ? '✓' : ''}</span></button></td>
							<td class="table-thumb-cell">
								<button
									class="table-thumb-select"
									onclick={() => loadItemAndClose(it)}
									disabled={historyManagerView !== 'active'}
									title={t().historyOpenItemTitle}
									aria-label={t().historyOpenItemTitle}
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
								<button
									class="thumb-star mini-star mini-mark"
									class:marked={!!it.for_revision}
									onclick={(event) => onToggleForRevision(it, event)}
									title={it.for_revision ? t().forRevisionOn : t().forRevisionOff}
									aria-label={it.for_revision ? t().forRevisionOn : t().forRevisionOff}
								>✎</button>
							</td>
							<td>
								{#if it.shared}<span class="shared-mark" title={isJapanese ? '他の利用者から共有された作品' : 'Shared with you by another member'}>{isJapanese ? '共有' : 'Shared'}</span>{/if}
								{#if hashLabel(it)}<button class="hash-chip table-hash" onclick={(event) => copyHash(it, event)} title={t().historyHashCopyTitle}>#{hashLabel(it)}</button>{/if}
							</td>
							<td>{formatHistoryDate(it.at)}</td>
							<td>{historyModelSummary(it)}</td>
							<td>{formatElapsed(it.elapsed_ms)}</td>
							<td>{catalogName(it.catalog_id)}</td>
							<td>
								{#if historyManagerView === 'active' && onShareItem && !it.shared}
									<button class="ghost-btn" onclick={() => onShareItem?.(it)} title={isJapanese ? 'この作品を共有する' : 'Share this work'}>{isJapanese ? '共有' : 'Share'}</button>
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

<style>
	/* Not a decoration: this listing is what people select and delete from, so a
	   work that belongs to someone else has to be legible as such at a glance. */
	.shared-mark {
		display: inline-block;
		margin-right: 0.35rem;
		padding: 0 0.35em;
		border: 1px solid var(--accent);
		border-radius: var(--btn-sm-radius);
		color: var(--accent);
		font-size: 0.75em;
		vertical-align: middle;
	}

	.lineage-history-list { flex: 1; min-height: 0; overflow: auto; padding: 10px 12px 16px; display: flex; flex-direction: column; gap: 10px; }
	.lineage-history-message { margin: auto; padding: 30px; color: var(--fg3); text-align: center; }
	.lineage-history-group { border: 1px solid var(--border); border-radius: var(--r-lg); background: var(--panel); overflow: hidden; }
	.lineage-history-group.current-lineage { border-color: var(--accent); box-shadow: 0 0 0 2px var(--accent-light); }
	.lineage-group-head { display: flex; align-items: center; gap: 10px; padding: 9px 10px; background: var(--panel); }
	.lineage-representative { flex: 0 0 56px; width: 56px; height: 56px; padding: 0; border: 0; border-radius: var(--r); overflow: hidden; background: var(--bg); cursor: pointer; }
	.lineage-representative :global(svg) { width: 100%; height: 100%; }
	.lineage-group-summary { flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 4px; }
	.lineage-group-summary strong { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; font-size: 12px; font-weight: 600; }
	.lineage-group-summary > span { color: var(--fg3); font-size: 10px; }
	.current-lineage-badge { align-self: flex-start; padding: 2px 6px; border-radius: 999px; background: var(--accent-light); color: var(--accent) !important; }
	.lineage-group-tools { display: flex; justify-content: flex-end; padding: 6px 10px; border-top: 1px solid var(--border); background: var(--bg); }
	.lineage-member-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(132px, 1fr)); gap: 8px; padding: 8px 10px 12px; border-top: 1px solid var(--border); background: var(--bg); }
	.lineage-member { position: relative; min-width: 0; padding: 5px; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel); }
	.lineage-member.selected, .lineage-member.current-work { border-color: var(--accent); }
	.lineage-member > .selection-checkbox { position: absolute; top: 8px; left: 8px; z-index: 5; }
	.lineage-member-main { width: 100%; min-width: 0; padding: 0; border: 0; background: transparent; color: var(--fg2); cursor: pointer; text-align: left; }
	.lineage-member-main :global(svg) { width: 100%; max-height: 110px; }
	.lineage-member-main span { display: block; overflow: hidden; margin-top: 4px; text-overflow: ellipsis; white-space: nowrap; font-size: 10px; }
	.lineage-member-actions { display: flex; align-items: center; gap: 4px; margin-top: 5px; }
	.lineage-member-actions .ghost-btn, .lineage-member-actions .danger-btn { margin-left: 0; }
	.lineage-history-list.list-mode .lineage-member-grid { display: flex; flex-direction: column; }
	.lineage-history-list.list-mode .lineage-member { display: grid; grid-template-columns: 18px minmax(0, 1fr) auto; align-items: center; gap: 8px; }
	.lineage-history-list.list-mode .lineage-member > .selection-checkbox { position: static; }
	.lineage-history-list.list-mode .lineage-member-main { display: grid; grid-template-columns: 48px minmax(0, 1fr); align-items: center; gap: 8px; }
	.lineage-history-list.list-mode .lineage-member-main :global(svg) { width: 48px; height: 48px; }
	.lineage-history-list.list-mode .lineage-member-main span { margin-top: 0; }
	/* Thumbnail tab, lineage mode: the works of one lineage have to read as one
	   run. A connector drawn between cards would break the moment the grid wraps,
	   so the run is carried by an enclosure instead -- a spine down the group's
	   left edge and one tinted shelf under its works -- plus the generation number
	   on each card, which survives any wrap. */
	.lineage-history-list.thumbs-mode .lineage-history-group { border-left: 3px solid var(--border); }
	.lineage-history-list.thumbs-mode .lineage-history-group.current-lineage { border-left-color: var(--accent); }
	.lineage-history-list.thumbs-mode .lineage-member-grid {
		background: color-mix(in srgb, var(--accent) 5%, var(--bg));
	}
	.lineage-generation-badge {
		position: absolute; top: 8px; right: 8px; z-index: 5;
		min-width: 16px; padding: 1px 5px;
		border-radius: 999px;
		background: var(--accent-light); color: var(--accent);
		font-size: 9px; line-height: 1.5; text-align: center;
		font-variant-numeric: tabular-nums;
	}
	/* A narrow window drops the works to one column; the spine and the shelf keep
	   the grouping legible when the grid can no longer show a row. */
	@media (max-width: 640px) {
		.lineage-history-list.thumbs-mode .lineage-member-grid { grid-template-columns: 1fr; }
		.lineage-history-list.thumbs-mode .lineage-group-head { flex-wrap: wrap; }
	}
	.history-group-tabs { flex-shrink: 0; }
	.modal-backdrop {
		position: fixed;
		inset: 0;
		z-index: 400;
		background: rgba(0,0,0,0.25);
		backdrop-filter: blur(2px);
	}
	.history-modal {
		position: fixed;
		top: 10vh;
		left: 10vw;
		z-index: 401;
		background: var(--panel2);
		border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		width: 80vw;
		height: 80vh;
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
	.catalog-modal-title {
		flex: 0 0 auto;
		font-size: 15px;
		font-weight: 300;
		letter-spacing: 0.05em;
	}
	.catalog-close {
		width: 24px;
		height: 24px;
		border: none;
		background: none;
		color: var(--fg3);
		font-size: 18px;
		cursor: pointer;
		line-height: 1;
	}
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
	.history-mode-tabs { flex-shrink: 0; }
	.history-manager-count {
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		margin-right: 2px;
	}
	.history-search {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--fg2);
		font-size: 12px;
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
		font-size: 12px;
		font-family: inherit;
	}
	.history-manager-pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
		color: var(--fg3);
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.history-nav-btn { min-width: 74px; }
	.history-latest-btn { min-width: 54px; }
	.history-thumb-grid-wrap,
	.history-table-wrap {
		flex: 1;
		padding: 8px 10px 6px;
		min-height: 0;
	}
	.history-thumb-grid-wrap { overflow: hidden; }
	.history-table-wrap { overflow: auto; }
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
	top: 26px;
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
	font: 600 10px/1 system-ui, sans-serif;
}
.selection-checkbox {
	box-sizing: border-box;
	width: 16px;
	height: 16px;
	display: inline-grid;
	place-items: center;
	margin: 0;
	padding: 0;
	border: 1px solid color-mix(in srgb, var(--fg) 32%, var(--border));
	border-radius: 3px;
	background: color-mix(in srgb, var(--panel) 92%, transparent);
	color: var(--accent-fg);
	cursor: pointer;
	font: 700 11px/1 system-ui, sans-serif;
	box-shadow: 0 1px 3px rgba(0,0,0,.16);
}
.selection-checkbox:hover { border-color: var(--accent); }
.selection-checkbox:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
.selection-checkbox.checked { border-color: var(--accent); background: var(--accent); }
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
		font-size: 14px;
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
		width: 18px;
		height: 18px;
		font-size: 11px;
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
	.thumb-catalog {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--fg2);
		font-size: 11px;
		line-height: 1.25;
	}
	.thumb-note { overflow: hidden; text-overflow: ellipsis; white-space: nowrap; color: var(--fg3); font-size: 10px; line-height: 1.25; }
	.thumb-note span { margin-right: 4px; font-weight: 600; }
	.thumb-action-row {
		display: flex;
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
		width: 18px;
		height: 18px;
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
	/* The revision mark sits beside the star and must not read as a second star:
	   a pencil, and the accent colour rather than the star colour. */
	.hash-row-mark {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg3);
		font-size: var(--btn-sm-font-size);
		line-height: 1;
		cursor: pointer;
	}
	.hash-row-mark.marked {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
	}
	.mini-mark.marked {
		border-color: var(--accent);
		background: var(--accent-light);
		color: var(--accent);
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
		font-size: 10px;
		line-height: 1;
		padding: 3px 7px;
		cursor: copy;
	}
	.hash-chip:hover {
		border-color: var(--accent);
		color: var(--fg);
	}
	.table-hash {
		font-size: 11px;
		white-space: nowrap;
	}
	/* Takes whatever the star and the hash chip leave; the native title carries
	   the whole string once the card is too narrow for it. */
	.thumb-model {
		flex: 1 1 auto;
		align-self: flex-end;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--fg3);
		font-size: 10px;
		line-height: 1.6;
	}
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
		border-collapse: collapse;
		background: var(--panel);
		font-size: 12px;
	}
	.history-table th,
	.history-table td {
		border: 1px solid var(--border);
		padding: 7px 8px;
		text-align: left;
		vertical-align: middle;
	}
	.history-table th { color: var(--fg3); font-weight: 500; background: var(--bg); }
	/* --action-* is the theme-aware primary pair; var(--fg) with a hardcoded
	   white label collapses to white-on-white in the dark theme. */
	.bulk-trash { min-width: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
	.bulk-trash svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
	.bulk-trash:disabled { opacity: .4; cursor: default; }
	.tool-count { margin-left: 4px; color: var(--fg3); }
	.tool-error { align-self: center; color: #b3452c; font-size: 11px; }
	.icon-trash-btn {
		width: 24px;
		height: 22px;
		padding: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: var(--fg2);
	}
	.icon-trash-btn svg {
		width: 22px;
		height: 20px;
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
