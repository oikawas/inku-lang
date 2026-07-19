<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { HistoryItem } from '$lib/historyManagerState.svelte';
	import HistoryThumbnail from './HistoryThumbnail.svelte';
	import AIRefineModal from './AIRefineModal.svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
	import ModelCardPicker from './ModelCardPicker.svelte';

	export type LineageNode = {
		id: string;
		state: 'active' | 'lineage_only' | 'tombstone';
		description_hash?: string | null;
		render_hash?: string | null;
		at: number;
		deleted_at?: number | null;
		child_count?: number;
		history?: HistoryItem | null;
	};
	export type LineageEdge = {
		id: string;
		parent_node_id: string;
		child_node_id: string;
		derivation_kind: string;
		metadata?: Record<string, unknown>;
	};
	export type LineageGraph = { focus_node_id: string; nodes: LineageNode[]; edges: LineageEdge[] };
	export type OkugakiItem = { id?: string; target_node_id: string; branch_snapshot: string[]; model: string; at: number; language: 'ja' | 'en'; body: string; warnings: string[] };

	type Props = {
		graph: LineageGraph | null;
		loading: boolean;
		error: string | null;
		isJapanese: boolean;
		onOpenNode: (node: LineageNode) => void | Promise<void>;
		onOpenRefinement: (node: LineageNode, view: 'adjust' | 'compare' | 'language') => void | Promise<void>;
		onDrawDescription: (node: LineageNode, text: string) => void | Promise<void>;
		onDrawDdl: (node: LineageNode, ddl: string) => void | Promise<void>;
		onOpenDdlEditor: (node: LineageNode) => void;
		onSaveOkugakiModel: (model: string) => void | Promise<void>;
		onPromoteNode: (node: LineageNode) => void | Promise<void>;
		onSaveNote: (node: LineageNode, note: string) => void | Promise<void>;
		onAskTrash: (historyIds: string[]) => void;
		onDetach: () => void;
		onLoadOverview: () => void | Promise<void>;
		onLoadBranch: (nodeId: string) => void | Promise<void>;
		onPaintOne: (text: string, options: any) => Promise<any>;
		onVisionAdvice: (historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) => Promise<any>;
		onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
		visionModel: string;
		okugakiModel: string;
		visionProviderGroups: ProviderGroup[];
	};
	type ArrowPath = { id: string; path: string; tombstone: boolean };

	let { graph, loading, error, isJapanese, onOpenNode, onOpenRefinement, onDrawDescription, onDrawDdl, onOpenDdlEditor, onSaveOkugakiModel, onPromoteNode, onSaveNote, onAskTrash, onDetach, onLoadOverview, onLoadBranch, onPaintOne, onVisionAdvice, onSaveVisionModel, visionModel, okugakiModel, visionProviderGroups }: Props = $props();

	// Standalone DDL-authored artworks carry the display_label marker 'DDL' and have
	// no natural-language instruction, so instruction-only refine paths are hidden.
	function isDdlOrigin(node: LineageNode): boolean {
		return node.history?.display_label === 'DDL';
	}
	let lineageColumnsEl = $state<HTMLDivElement | null>(null);
	let resizeObserver: ResizeObserver | null = null;
	let arrowFrame: number | null = null;
	let arrowPaths = $state<ArrowPath[]>([]);
	let checkedHistoryIds = $state<string[]>([]);
	let noteDrafts = $state<Record<string, string>>({});
	let savingNoteIds = $state<string[]>([]);
	let expandedNodeIds = $state<string[]>([]);
	let lastFocusNodeId = $state<string | null>(null);
	let overviewOpen = $state(false);
	let overviewLoading = $state(false);
	let overviewScale = $state(1);
	let activeMenuNodeId = $state<string | null>(null);
	let activeAIRefineNode = $state<LineageNode | null>(null);
	let activeEditNode = $state<LineageNode | null>(null);
	let editMode = $state<'description' | 'ddl' | null>(null);
	let editDraft = $state('');
	let editDrawing = $state(false);
	let editError = $state<string | null>(null);
	let okugakiOpen = $state(false);
	let selectedOkugakiModel = $state('');
	let okugakiItems = $state<OkugakiItem[]>([]);
	let okugakiLoading = $state(false);
	let okugakiGenerating = $state(false);
	let okugakiError = $state<string | null>(null);
	let okugakiLoadedTarget = $state<string | null>(null);
	const cardElements = new Map<string, HTMLElement>();

	const nodeById = $derived(new Map((graph?.nodes ?? []).map((node) => [node.id, node])));
	const focusNode = $derived(graph?.nodes.find((node) => node.id === graph.focus_node_id) ?? null);
	const edgeByChild = $derived(new Map((graph?.edges ?? []).map((edge) => [edge.child_node_id, edge])));
	const childrenByParent = $derived.by(() => {
		const children = new Map<string, LineageNode[]>();
		for (const edge of graph?.edges ?? []) {
			const child = nodeById.get(edge.child_node_id);
			if (child) children.set(edge.parent_node_id, [...(children.get(edge.parent_node_id) ?? []), child]);
		}
		return children;
	});
	const depthByNode = $derived.by(() => {
		const depths = new Map<string, number>();
		const resolve = (id: string, seen = new Set<string>()): number => {
			if (depths.has(id)) return depths.get(id) ?? 0;
			if (seen.has(id)) return 0;
			seen.add(id);
			const parent = edgeByChild.get(id)?.parent_node_id;
			const depth = parent ? resolve(parent, seen) + 1 : 0;
			depths.set(id, depth);
			return depth;
		};
		for (const node of graph?.nodes ?? []) resolve(node.id);
		return depths;
	});
	const ancestorIds = $derived.by(() => {
		const ids = new Set<string>();
		let current = graph?.focus_node_id ?? null;
		while (current && !ids.has(current)) {
			ids.add(current);
			current = edgeByChild.get(current)?.parent_node_id ?? null;
		}
		return ids;
	});
	const visibleNodeIds = $derived.by(() => {
		if (overviewOpen) return new Set((graph?.nodes ?? []).map((node) => node.id));
		const visible = new Set(ancestorIds);
		const queue = [...ancestorIds];
		const expanded = new Set(expandedNodeIds);
		while (queue.length) {
			const parentId = queue.shift() as string;
			if (!expanded.has(parentId)) continue;
			for (const child of childrenByParent.get(parentId) ?? []) {
				if (visible.has(child.id)) continue;
				visible.add(child.id);
				queue.push(child.id);
			}
		}
		return visible;
	});
	const columns = $derived.by(() => {
		const grouped = new Map<number, LineageNode[]>();
		for (const node of graph?.nodes ?? []) {
			if (!visibleNodeIds.has(node.id)) continue;
			const depth = depthByNode.get(node.id) ?? 0;
			grouped.set(depth, [...(grouped.get(depth) ?? []), node]);
		}
		return [...grouped.entries()].sort(([a], [b]) => a - b);
	});

	function shortHash(value?: string | null): string {
		if (!value) return '—';
		const [prefix, digest] = value.split(':', 2);
		return digest ? `${prefix}:${digest.slice(0, 10)}…` : `${value.slice(0, 12)}…`;
	}

	function operationLabel(kind?: string): string {
		const ja: Record<string, string> = { touch_variation: 'タッチ', layout_variation: '構図', catalog_change: '色', reinterpretation: '解釈', model_variation: 'モデル', language_variation: '言語', ddl_edit: 'DDL編集', description_edit: '記述編集', replay: '再描画', canvas_aspect_change: 'キャンバス変更' };
		const en: Record<string, string> = { touch_variation: 'Touch', layout_variation: 'Layout', catalog_change: 'Color', reinterpretation: 'Reading', model_variation: 'Model', language_variation: 'Language', ddl_edit: 'DDL edit', description_edit: 'Description edit', replay: 'Replay', canvas_aspect_change: 'Canvas change' };
		return (isJapanese ? ja : en)[kind ?? ''] ?? (kind || (isJapanese ? '起点' : 'Root'));
	}

function toggleCheckedHistory(historyId: string): void {
	checkedHistoryIds = checkedHistoryIds.includes(historyId)
		? checkedHistoryIds.filter((id) => id !== historyId)
		: [...checkedHistoryIds, historyId];
}

function askTrashChecked(): void {
	if (checkedHistoryIds.length > 0) onAskTrash([...checkedHistoryIds]);
}

function noteValue(node: LineageNode): string {
	return noteDrafts[node.id] ?? node.history?.note ?? '';
}

function updateNoteDraft(nodeId: string, value: string): void {
	noteDrafts = { ...noteDrafts, [nodeId]: value };
}

async function saveNodeNote(node: LineageNode): Promise<void> {
	if (!node.history?.id || savingNoteIds.includes(node.id)) return;
	savingNoteIds = [...savingNoteIds, node.id];
	try {
		await onSaveNote(node, noteValue(node));
		const next = { ...noteDrafts };
		delete next[node.id];
		noteDrafts = next;
	} finally {
		savingNoteIds = savingNoteIds.filter((id) => id !== node.id);
	}
}

	async function openNode(node: LineageNode): Promise<void> {
		if (overviewOpen) closeOverview();
		await onOpenNode(node);
	}

	async function loadOkugaki(force = false): Promise<void> {
		const nodeId = graph?.focus_node_id;
		if (!nodeId || (!force && okugakiLoadedTarget === nodeId)) return;
		okugakiLoading = true;
		okugakiError = null;
		try {
			const response = await fetch(`/api/lineage/${encodeURIComponent(nodeId)}/okugaki`, { credentials: 'include', cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			okugakiItems = await response.json();
			okugakiLoadedTarget = nodeId;
		} catch (cause) {
			okugakiError = cause instanceof Error ? cause.message : String(cause);
		} finally {
			okugakiLoading = false;
		}
	}

	function createIdempotencyKey(): string {
		if (typeof globalThis.crypto?.randomUUID === 'function') return globalThis.crypto.randomUUID();
		const bytes = new Uint8Array(16);
		if (typeof globalThis.crypto?.getRandomValues === 'function') {
			globalThis.crypto.getRandomValues(bytes);
		} else {
			for (let index = 0; index < bytes.length; index += 1) bytes[index] = Math.floor(Math.random() * 256);
		}
		bytes[6] = (bytes[6] & 0x0f) | 0x40;
		bytes[8] = (bytes[8] & 0x3f) | 0x80;
		const hex = Array.from(bytes, (value) => value.toString(16).padStart(2, '0')).join('');
		return `${hex.slice(0, 8)}-${hex.slice(8, 12)}-${hex.slice(12, 16)}-${hex.slice(16, 20)}-${hex.slice(20)}`;
	}

	async function generateOkugaki(): Promise<void> {
		const nodeId = graph?.focus_node_id;
		if (!nodeId || !selectedOkugakiModel.trim() || okugakiGenerating) return;
		okugakiGenerating = true;
		okugakiError = null;
		try {
			const response = await fetch(`/api/lineage/${encodeURIComponent(nodeId)}/okugaki`, {
				method: 'POST', credentials: 'include', headers: { 'Content-Type': 'application/json', 'Idempotency-Key': createIdempotencyKey() },
				body: JSON.stringify({ model: selectedOkugakiModel.trim(), language: isJapanese ? 'ja' : 'en', save: true })
			});
			if (!response.ok) {
				const payload = await response.json().catch(() => null) as { detail?: string } | null;
				throw new Error(payload?.detail || `HTTP ${response.status}`);
			}
			okugakiItems = [...okugakiItems, await response.json()];
			okugakiLoadedTarget = nodeId;
		} catch (cause) {
			okugakiError = cause instanceof Error ? cause.message : String(cause);
		} finally {
			okugakiGenerating = false;
		}
	}

	async function deleteOkugaki(item: OkugakiItem): Promise<void> {
		if (!item.id || !confirm(t().okugakiDeleteConfirm)) return;
		const response = await fetch(`/api/okugaki/${encodeURIComponent(item.id)}`, { method: 'DELETE', credentials: 'include' });
		if (response.ok) okugakiItems = okugakiItems.filter((entry) => entry.id !== item.id);
		else okugakiError = (await response.text()) || `HTTP ${response.status}`;
	}

	function openEditDialog(node: LineageNode, mode: 'description' | 'ddl'): void {
		if (!node.history) return;
		activeEditNode = node;
		editMode = mode;
		editDraft = mode === 'description'
			? (node.history.source_text ?? node.history.input ?? '')
			: (node.history.ddl ?? '');
		editError = null;
		activeMenuNodeId = null;
	}

	function closeEditDialog(): void {
		if (editDrawing) return;
		activeEditNode = null;
		editMode = null;
		editDraft = '';
		editError = null;
	}

	async function drawEditedArtwork(): Promise<void> {
		if (!activeEditNode || !editMode || !editDraft.trim() || editDrawing) return;
		editDrawing = true;
		editError = null;
		try {
			if (editMode === 'description') await onDrawDescription(activeEditNode, editDraft);
			else await onDrawDdl(activeEditNode, editDraft);
			activeEditNode = null;
			editMode = null;
			editDraft = '';
		} catch (cause) {
			editError = cause instanceof Error ? cause.message : String(cause);
		} finally {
			editDrawing = false;
		}
	}

	async function selectOkugakiModel(provider: Provider, model: string): Promise<void> {
		const nextModel = qualifiedModelId(provider, model);
		const previous = selectedOkugakiModel;
		selectedOkugakiModel = nextModel;
		okugakiError = null;
		try {
			await onSaveOkugakiModel(nextModel);
		} catch (cause) {
			selectedOkugakiModel = previous;
			okugakiError = cause instanceof Error ? cause.message : String(cause);
		}
	}

	function handleDialogKeydown(event: KeyboardEvent): void {
		if (event.key !== 'Escape') return;
		if (activeEditNode && !editDrawing) closeEditDialog();
		else if (okugakiOpen && !okugakiGenerating) okugakiOpen = false;
	}

	async function toggleBranch(node: LineageNode): Promise<void> {
		if (expandedNodeIds.includes(node.id)) {
			expandedNodeIds = expandedNodeIds.filter((id) => id !== node.id);
			return;
		}
		const loadedCount = childrenByParent.get(node.id)?.length ?? 0;
		if ((node.child_count ?? loadedCount) > loadedCount) await onLoadBranch(node.id);
		expandedNodeIds = [...expandedNodeIds, node.id];
	}
	async function openOverview(): Promise<void> {
		overviewOpen = true;
		overviewLoading = true;
		try { await onLoadOverview(); }
		finally { overviewLoading = false; await tick(); scheduleArrowUpdate(); }
	}
	function closeOverview(): void {
		overviewOpen = false;
		overviewScale = 1;
		void tick().then(scheduleArrowUpdate);
	}
	function getRelativeCoords(el: HTMLElement, container: HTMLElement): { left: number; top: number; width: number; height: number } {
		let left = 0;
		let top = 0;
		const width = el.offsetWidth;
		const height = el.offsetHeight;
		let curr: HTMLElement | null = el;
		while (curr && curr !== container) {
			left += curr.offsetLeft;
			top += curr.offsetTop;
			left -= curr.scrollLeft || 0;
			top -= curr.scrollTop || 0;
			curr = curr.offsetParent as HTMLElement | null;
		}
		return { left, top, width, height };
	}

	function updateArrowPaths(): void {
		if (!lineageColumnsEl || !graph) {
			arrowPaths = [];
			return;
		}
		const container = lineageColumnsEl;
		arrowPaths = graph.edges.flatMap((edge) => {
			if (!visibleNodeIds.has(edge.parent_node_id) || !visibleNodeIds.has(edge.child_node_id)) return [];
			const parent = cardElements.get(edge.parent_node_id);
			const child = cardElements.get(edge.child_node_id);
			if (!parent || !child) return [];
			const parentRect = getRelativeCoords(parent, container);
			const childRect = getRelativeCoords(child, container);
			const x1 = parentRect.left + parentRect.width / 2;
			const y1 = parentRect.top + parentRect.height + 1;
			const x2 = childRect.left + childRect.width / 2;
			const y2 = childRect.top - 7;
			const bend = Math.max(18, (y2 - y1) / 2);
			return [{
				id: edge.id,
				path: `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`,
				tombstone: nodeById.get(edge.parent_node_id)?.state === 'tombstone' || nodeById.get(edge.child_node_id)?.state === 'tombstone',
			}];
		});
	}

	function scheduleArrowUpdate(): void {
		if (typeof window === 'undefined') return;
		if (arrowFrame !== null) window.cancelAnimationFrame(arrowFrame);
		arrowFrame = window.requestAnimationFrame(() => {
			arrowFrame = null;
			updateArrowPaths();
		});
	}

	function registerCard(element: HTMLElement, nodeId: string) {
		cardElements.set(nodeId, element);
		resizeObserver?.observe(element);
		scheduleArrowUpdate();
		return {
			update(nextNodeId: string) {
				if (nextNodeId === nodeId) return;
				cardElements.delete(nodeId);
				nodeId = nextNodeId;
				cardElements.set(nodeId, element);
				scheduleArrowUpdate();
			},
			destroy() {
				resizeObserver?.unobserve(element);
				cardElements.delete(nodeId);
				scheduleArrowUpdate();
			},
		};
	}

	function handleGlobalClick() {
		activeMenuNodeId = null;
	}

	onMount(() => {
		resizeObserver = new ResizeObserver(scheduleArrowUpdate);
		if (lineageColumnsEl) resizeObserver.observe(lineageColumnsEl);
		for (const element of cardElements.values()) resizeObserver.observe(element);
		window.addEventListener('resize', scheduleArrowUpdate);
		window.addEventListener('click', handleGlobalClick);
		scheduleArrowUpdate();
		return () => {
			resizeObserver?.disconnect();
			resizeObserver = null;
			window.removeEventListener('resize', scheduleArrowUpdate);
			window.removeEventListener('click', handleGlobalClick);
			if (arrowFrame !== null) window.cancelAnimationFrame(arrowFrame);
		};
	});

	$effect(() => {
		const focusId = graph?.focus_node_id ?? null;
		const focusChanged = !!focusId && focusId !== lastFocusNodeId;
		if (focusChanged) { lastFocusNodeId = focusId; expandedNodeIds = [focusId]; }
		columns;
		overviewScale;
		void tick().then(() => {
			scheduleArrowUpdate();
			if (focusChanged && focusId && !overviewOpen) {
				cardElements.get(focusId)?.scrollIntoView({ behavior: 'smooth', block: 'center', inline: 'center' });
			}
		});
	});
$effect(() => {
	const available = new Set((graph?.nodes ?? [])
		.filter((node) => node.history?.id && !node.history.trashed)
		.map((node) => node.history?.id as string));
	const next = checkedHistoryIds.filter((id) => available.has(id));
	if (next.join('\n') !== checkedHistoryIds.join('\n')) checkedHistoryIds = next;
});
$effect(() => {
	const target = graph?.focus_node_id ?? null;
	if (target && target !== okugakiLoadedTarget) void loadOkugaki();
});

</script>

<svelte:window onkeydown={handleDialogKeydown} />

<section class="lineage-panel" class:overview={overviewOpen}>
	<header>
		<div>
			<h2>{isJapanese ? '作品の系譜' : 'Artwork Lineage'}</h2>
			<p>{overviewOpen ? (isJapanese ? '全体を上から下へ見渡せます。' : 'Review the complete tree from top to bottom.') : (isJapanese ? '表示中の作品を中心に、祖先から子作品へ上から下に辿れます。' : 'Trace ancestors and descendants from top to bottom.')}</p>
			{#if graph}<p class="lineage-context">{isJapanese ? '表示中の作品が、次の推敲の親になります。' : 'The displayed artwork will be the parent of your next refinement.'}</p>{/if}
		</div>
<div class="lineage-actions">
	<button type="button" disabled={!graph?.focus_node_id} title={t().okugakiTooltip} onclick={() => { selectedOkugakiModel = okugakiModel || visionModel; okugakiOpen = true; void loadOkugaki(true); }}>{t().okugakiRead}</button>
	{#if overviewOpen}
		<div class="overview-zoom"><button type="button" onclick={() => (overviewScale = Math.max(.4, overviewScale - .1))}>−</button><span>{Math.round(overviewScale * 100)}%</span><button type="button" onclick={() => (overviewScale = Math.min(1.4, overviewScale + .1))}>＋</button></div>
		<button type="button" onclick={closeOverview}>{isJapanese ? '通常表示へ戻る' : 'Close overview'}</button>
	{:else}
		<button type="button" onclick={openOverview}>{isJapanese ? '全体図' : 'Overview'}</button>
	{/if}
	<button class="bulk-trash" type="button" disabled={checkedHistoryIds.length === 0} title={isJapanese ? 'チェックした作品をゴミ箱へ移動' : 'Move checked artworks to trash'} aria-label={isJapanese ? 'チェックした作品をゴミ箱へ移動' : 'Move checked artworks to trash'} onclick={askTrashChecked}>
		<svg viewBox="2 2 20 20" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M6 6l1 15h10l1-15"></path><path d="M10 10v7"></path><path d="M14 10v7"></path></svg>
		{#if checkedHistoryIds.length > 0}<span>{checkedHistoryIds.length}</span>{/if}
	</button>
	<button type="button" class="detach-btn" onclick={onDetach}>{isJapanese ? '新しい起点にする' : 'Start a new root'}</button>
</div>
	</header>
	{#if loading || overviewLoading}
		<div class="lineage-message">{isJapanese ? '系譜を読み込み中…' : 'Loading lineage…'}</div>
	{:else if error}
		<div class="lineage-message error">{error}</div>
	{:else if !graph || graph.nodes.length === 0}
		<div class="lineage-message">{isJapanese ? '保存すると、ここに系譜が表示されます。' : 'Save an artwork to begin its lineage.'}</div>
	{:else}
		<div class="lineage-scroll" class:overview-scroll={overviewOpen}>
			<div class="lineage-columns" bind:this={lineageColumnsEl} style={overviewOpen ? `transform: scale(${overviewScale}); transform-origin: top left; width: ${100 / overviewScale}%; height: ${100 / overviewScale}%;` : undefined}>
				<svg class="lineage-arrows" aria-hidden="true">
					<defs>
						<marker id="lineage-arrowhead" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth">
							<path d="M 0 0 L 7 3.5 L 0 7 z"></path>
						</marker>
					</defs>
					{#each arrowPaths as arrow (arrow.id)}
						<path class="lineage-arrow" class:tombstone-arrow={arrow.tombstone} d={arrow.path} marker-end="url(#lineage-arrowhead)"></path>
					{/each}
				</svg>
				{#each columns as [depth, nodes] (depth)}
					<div class="lineage-column" class:menu-layer={nodes.some((node) => node.id === activeMenuNodeId)}>
						<div class="generation">{isJapanese ? `第${depth + 1}世代` : `Generation ${depth + 1}`}</div>
						{#each nodes as node (node.id)}
							{@const edge = edgeByChild.get(node.id)}
							{@const childCount = node.child_count ?? childrenByParent.get(node.id)?.length ?? 0}
							<article use:registerCard={node.id} class="lineage-card" class:focus={node.id === graph.focus_node_id} class:tombstone={node.state === 'tombstone'} class:trashed={!!node.history?.trashed} class:menu-open={node.id === activeMenuNodeId}>
<div class="card-toolbar">
{#if node.history?.id && !node.history.trashed}
	<label class="card-check" aria-label={isJapanese ? '一括操作の対象にする' : 'Check for bulk actions'}>
		<input type="checkbox" checked={checkedHistoryIds.includes(node.history.id)} onclick={(event) => event.stopPropagation()} onpointerdown={(event) => event.stopPropagation()} onchange={() => toggleCheckedHistory(node.history?.id as string)} />
	</label>
	{/if}
	<span class="identity-marks">
		{#if node.id === graph.focus_node_id}<span class="active-mark">{isJapanese ? '表示中' : 'Displayed'}</span>{/if}
		{#if node.state === 'lineage_only'}<span class="identity-mark">{isJapanese ? '中間作品・履歴非表示' : 'Intermediate · hidden from history'}</span>{/if}
		{#if node.id !== graph.focus_node_id && node.description_hash && node.description_hash === focusNode?.description_hash}<span class="identity-mark">{isJapanese ? '同じ記述' : 'Same text'}</span>{/if}
		{#if node.id !== graph.focus_node_id && node.render_hash && node.render_hash === focusNode?.render_hash}<span class="identity-mark">{isJapanese ? '同じ版' : 'Same edition'}</span>{/if}
	</span>
{#if node.history?.id && !node.history.trashed}
	<button type="button" class="card-menu-trigger" onclick={(event) => { event.stopPropagation(); activeMenuNodeId = activeMenuNodeId === node.id ? null : node.id; }} aria-label={isJapanese ? 'メニューを開く' : 'Open menu'}>
		<svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round"><circle cx="12" cy="12" r="1"></circle><circle cx="19" cy="12" r="1"></circle><circle cx="5" cy="12" r="1"></circle></svg>
	</button>
	{#if activeMenuNodeId === node.id}
		{@const ddlOrigin = isDdlOrigin(node)}
		<div class="card-dropdown-menu" role="menu">
			{#if !ddlOrigin}
				<button type="button" role="menuitem" onclick={(event) => { event.stopPropagation(); openEditDialog(node, 'description'); }}>
					{isJapanese ? '記述を編集' : 'Edit description'}
				</button>
			{/if}
			<button type="button" role="menuitem" onclick={(event) => { event.stopPropagation(); onOpenDdlEditor(node); activeMenuNodeId = null; }}>
				{isJapanese ? 'DDLを編集' : 'Edit DDL'}
			</button>
			<button type="button" role="menuitem" onclick={(event) => { event.stopPropagation(); activeAIRefineNode = node; activeMenuNodeId = null; }}>
				{isJapanese ? 'AIに自律推敲させる...' : 'AI Refine...'}
			</button>
			<button type="button" role="menuitem" onclick={(event) => { event.stopPropagation(); void onOpenRefinement(node, 'adjust'); activeMenuNodeId = null; }}>
				{isJapanese ? '描画要素で比較' : 'Compare drawing elements'}
			</button>
			{#if !ddlOrigin}
				<button type="button" role="menuitem" onclick={(event) => { event.stopPropagation(); void onOpenRefinement(node, 'compare'); activeMenuNodeId = null; }}>
					{isJapanese ? 'モデルで比較' : 'Compare models'}
				</button>
				<button type="button" role="menuitem" onclick={(event) => { event.stopPropagation(); void onOpenRefinement(node, 'language'); activeMenuNodeId = null; }}>
					{isJapanese ? '言語で比較' : 'Compare languages'}
				</button>
			{/if}
		</div>
	{/if}
{/if}
</div>

								<button type="button" class="card-main" disabled={!node.history} aria-current={node.id === graph.focus_node_id ? 'true' : undefined} aria-label={node.history ? `${operationLabel(edge?.derivation_kind)}: ${node.history.source_text ?? node.history.input}` : (isJapanese ? '削除された作品' : 'Deleted artwork')} onclick={() => openNode(node)}>
									<div class="operation">
										<span>{operationLabel(edge?.derivation_kind)}</span>
									</div>
									<div class="preview">
										{#if node.history?.svg}<HistoryThumbnail item={node.history} scope={`lineage-${node.id}`} size="manager" />{:else}<span>{isJapanese ? '削除済み' : 'Deleted'}</span>{/if}
									</div>
									{#if node.history?.display_label}<div class="display-label">{node.history.display_label}</div>{/if}
									{#if node.history?.trashed}<div class="trash-state">{isJapanese ? 'ゴミ箱（復元可能）' : 'In trash (restorable)'}</div>{/if}
									<div class="meta" title={node.history?.source_text ?? node.history?.input ?? node.description_hash ?? ''}>{node.history?.source_text || node.history?.input || (isJapanese ? '削除された作品' : 'Deleted artwork')}</div>
								</button>
								{#if childCount > 0 && !overviewOpen}
									<button class="branch-toggle" type="button" aria-expanded={expandedNodeIds.includes(node.id)} onclick={() => toggleBranch(node)}>{expandedNodeIds.includes(node.id) ? '▾' : '▸'} {isJapanese ? `子作品 ${childCount}件` : `${childCount} children`}</button>
								{/if}
								{#if node.history && !overviewOpen}
									<details class="node-details">
										<summary>{isJapanese ? '詳細' : 'Details'}</summary>
										<dl>
											<dt>{isJapanese ? '記述' : 'Text'}</dt><dd class="full-source">{node.history.source_text ?? node.history.input}</dd>
											<dt>dh1</dt><dd>{shortHash(node.description_hash)}</dd>
											<dt>rh2</dt><dd>{shortHash(node.render_hash)}</dd>
											<dt>Stage 1</dt><dd>{node.history.stage1_model ?? '—'}</dd>
											<dt>Stage 2</dt><dd>{node.history.stage2_model ?? '—'}</dd>
											<dt>seed</dt><dd>{node.history.render_seed ?? '—'} / {node.history.vary_seed ?? '—'} / {node.history.interpretation_seed ?? '—'}</dd>
											<dt>{isJapanese ? '派生' : 'Derived by'}</dt><dd>{operationLabel(edge?.derivation_kind)}</dd>
										</dl>
										<div class="note-editor">
										<label for={`lineage-note-${node.id}`}>{isJapanese ? '作品へのコメント' : 'Artwork Comment'}</label>
											<textarea id={`lineage-note-${node.id}`} maxlength="240" rows="3" value={noteValue(node)} disabled={savingNoteIds.includes(node.id)} oninput={(event) => updateNoteDraft(node.id, event.currentTarget.value)}></textarea>
											<button type="button" disabled={savingNoteIds.includes(node.id) || noteValue(node).trim() === (node.history?.note ?? '').trim()} onclick={() => saveNodeNote(node)}>{savingNoteIds.includes(node.id) ? (isJapanese ? '保存中…' : 'Saving…') : (isJapanese ? '保存' : 'Save')}</button>
										</div>
									</details>
								{/if}
								{#if node.state === 'lineage_only'}<button class="promote" type="button" onclick={() => onPromoteNode(node)}>{isJapanese ? '通常履歴に保存' : 'Save to regular history'}</button>{/if}
							</article>
						{/each}
					</div>
				{/each}
			</div>
		</div>
		<ol class="sr-only" aria-label={isJapanese ? '作品系譜の階層一覧' : 'Artwork lineage hierarchy'}>
			{#each graph.nodes as node (node.id)}
				{@const edge = edgeByChild.get(node.id)}
				<li>{node.id === graph.focus_node_id ? (isJapanese ? '表示中 — ' : 'Displayed — ') : ''}{operationLabel(edge?.derivation_kind)} — {node.history?.source_text ?? node.history?.input ?? (isJapanese ? '削除された作品' : 'Deleted artwork')}</li>
			{/each}
		</ol>
	{/if}
</section>

{#if activeEditNode && editMode}
	<button type="button" class="lineage-edit-backdrop" aria-label={isJapanese ? '編集ダイアログを閉じる' : 'Close edit dialog'} disabled={editDrawing} onclick={closeEditDialog}></button>
	<div class="lineage-edit-dialog" role="dialog" aria-modal="true" aria-labelledby="lineage-edit-title" tabindex="-1">
			<header>
				<div>
					<h2 id="lineage-edit-title">{editMode === 'description' ? (isJapanese ? '記述を編集' : 'Edit description') : (isJapanese ? 'DDLを編集' : 'Edit DDL')}</h2>
					<p>{isJapanese ? '描画すると、選択した作品の子として系譜へ保存します。' : 'Drawing saves a new child of the selected artwork.'}</p>
				</div>
				<button type="button" disabled={editDrawing} aria-label={isJapanese ? '閉じる' : 'Close'} onclick={closeEditDialog}>×</button>
			</header>
			<div class="lineage-edit-body">
				<label for="lineage-edit-text">{editMode === 'description' ? (isJapanese ? '記述' : 'Description') : 'DDL'}</label>
				<textarea id="lineage-edit-text" class:ddl-editor={editMode === 'ddl'} rows={editMode === 'ddl' ? 18 : 9} bind:value={editDraft} spellcheck={editMode === 'description'} disabled={editDrawing}></textarea>
				{#if editError}<div class="lineage-message error">{editError}</div>{/if}
			</div>
			<footer>
				<button type="button" disabled={editDrawing} onclick={closeEditDialog}>{isJapanese ? 'キャンセル' : 'Cancel'}</button>
				<button type="button" class="edit-draw" disabled={editDrawing || !editDraft.trim()} onclick={drawEditedArtwork}>{editDrawing ? (isJapanese ? '描画中…' : 'Drawing…') : (isJapanese ? '描画' : 'Draw')}</button>
			</footer>
	</div>
{/if}

{#if okugakiOpen}
	<div class="okugaki-backdrop" role="presentation">
		<div class="okugaki-dialog" role="dialog" aria-modal="true" aria-labelledby="okugaki-title" tabindex="-1">
			<header><div><h2 id="okugaki-title">{t().okugakiTitle}</h2><p>{t().okugakiDescription}</p></div><button type="button" disabled={okugakiGenerating} onclick={() => (okugakiOpen = false)}>×</button></header>
			<div class="okugaki-controls">
				<p>{t().okugakiBranchConfirm.replace('{count}', String(ancestorIds.size))}</p>
				<ModelCardPicker label={t().okugakiModel} selectedModel={selectedOkugakiModel} providerGroups={visionProviderGroups} disabled={okugakiGenerating} onSelect={(provider: Provider, model: string) => void selectOkugakiModel(provider, model)} />
				<button class="okugaki-generate" type="button" disabled={okugakiGenerating || !selectedOkugakiModel.trim()} onclick={generateOkugaki}>{okugakiGenerating ? t().okugakiReading : t().okugakiAppend}</button>
				{#if okugakiGenerating}<div class="okugaki-progress" aria-live="polite"><span></span>{t().okugakiProgress}</div>{/if}
				{#if okugakiError}<div class="lineage-message error">{okugakiError}</div>{/if}
			</div>
			<div class="okugaki-list">
				{#if okugakiLoading}<div class="lineage-message">{t().okugakiLoading}</div>
				{:else if okugakiItems.length === 0}<div class="lineage-message">{t().okugakiEmpty}</div>
				{:else}{#each okugakiItems as item (item.id ?? item.at)}
					<article class="okugaki-record"><div class="okugaki-record-head"><time>{new Date(item.at).toLocaleString(isJapanese ? 'ja-JP' : 'en-US')}</time>{#if item.id}<button type="button" title={t().okugakiDelete} onclick={() => deleteOkugaki(item)}>×</button>{/if}</div><div class="okugaki-body">{item.body}</div>{#if item.warnings.length}<div class="okugaki-warning">{t().okugakiWarning}: {item.warnings.join(', ')}</div>{/if}</article>
				{/each}{/if}
			</div>
		</div>
	</div>
{/if}

{#if activeAIRefineNode}
	<AIRefineModal
		node={activeAIRefineNode}
		onClose={() => (activeAIRefineNode = null)}
		{onPaintOne}
		{onVisionAdvice}
		{onSaveVisionModel}
		{visionModel}
		{visionProviderGroups}
		onLoadBranch={onLoadBranch}
	/>
{/if}


<style>
	.lineage-panel { box-sizing: border-box; width: 100%; height: 100%; min-width: 0; padding: 22px; overflow: hidden; display: flex; flex-direction: column; color: var(--fg); background: var(--bg); }
	.lineage-panel.overview { position: fixed; inset: 14px; z-index: 1300; width: auto; height: auto; border: 1px solid var(--border2); border-radius: 12px; box-shadow: 0 18px 70px #000a; }
	header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
	h2 { margin: 0 0 4px; font-size: 1.05rem; }
	p { margin: 0; color: var(--fg3); font-size: .82rem; }
	.lineage-context { margin-top: 5px; color: var(--fg2); font-weight: 600; }
	.lineage-actions, .overview-zoom { display: flex; align-items: center; gap: 8px; }
	.overview-zoom { padding-right: 8px; border-right: 1px solid var(--border); }
	.overview-zoom span { min-width: 42px; color: var(--fg3); font-size: .72rem; text-align: center; }
	header button, .promote, .branch-toggle { border: 1px solid var(--border2); background: var(--panel); color: var(--fg); border-radius: 7px; padding: 7px 10px; cursor: pointer; }
	.detach-btn { background: #fff7e8; border-color: #d8b36a; color: #6c4a10; font-weight: 600; box-shadow: 0 1px 3px rgba(108,74,16,0.12); }
	.detach-btn:hover { background: #ffefd0; border-color: #bd8f34; color: #4f360b; }
	.bulk-trash { min-width: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
	.bulk-trash svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
	.bulk-trash:disabled { opacity: .4; cursor: default; }
	.lineage-message { margin: auto; color: var(--fg3); }
	.lineage-message.error { color: var(--danger, #9b3d32); }
	.lineage-scroll { min-height: 0; overflow-x: hidden; overflow-y: auto; padding: 8px 18px 24px 8px; }
	.lineage-columns { position: relative; width: 100%; display: flex; flex-direction: column; align-items: stretch; gap: 58px; transform-origin: top center; }
	.lineage-arrows { position: absolute; inset: 0; z-index: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
	.lineage-arrow { fill: none; stroke: color-mix(in srgb, var(--fg2) 72%, transparent); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
	.lineage-arrow.tombstone-arrow { stroke-dasharray: 5 4; }
	.lineage-arrows marker path { fill: var(--fg2); }
	.lineage-column { position: relative; z-index: 1; width: 100%; min-width: 0; display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: center; gap: 14px 18px; }
	.lineage-column.menu-layer { z-index: 20; }
	.generation { flex: 0 0 100%; color: var(--fg3); font-size: .72rem; text-align: center; }
	.lineage-card { position: relative; box-sizing: border-box; width: 210px; min-width: 0; max-width: 210px; overflow: hidden; border: 1px solid var(--border); border-radius: 10px; padding: 8px; background: var(--panel); box-shadow: 0 2px 8px color-mix(in srgb, var(--fg) 8%, transparent); }
	.lineage-card.menu-open { z-index: 10; overflow: visible; }
	.lineage-card.focus { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--panel)); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 22%, transparent); }
	.lineage-card.tombstone { border-style: dashed; opacity: .72; }
	.lineage-card.trashed { opacity: .62; filter: grayscale(.35); }
	.card-toolbar { position: relative; z-index: 3; min-height: 22px; margin-bottom: 6px; padding-right: 26px; display: flex; align-items: flex-start; gap: 5px; }
	.card-check { flex: 0 0 auto; display: grid; place-items: center; padding: 2px; border-radius: 4px; background: color-mix(in srgb, var(--panel) 88%, transparent); cursor: pointer; }
	.card-check input { width: 15px; height: 15px; margin: 0; accent-color: var(--accent); margin: 0; }
	.lineage-edit-backdrop { position: fixed; inset: 0; z-index: 1460; width: 100%; height: 100%; border: 0; padding: 0; background: #0009; cursor: default; }
	.lineage-edit-dialog { position: fixed; z-index: 1461; top: 50%; left: 50%; transform: translate(-50%, -50%); box-sizing: border-box; width: min(780px, 96vw); max-height: 92vh; overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 24px 80px #000a; }
	.lineage-edit-dialog > header { padding: 18px 20px 14px; margin: 0; border-bottom: 1px solid var(--border); }
	.lineage-edit-dialog > header button { border: 0; background: transparent; color: var(--fg2); font-size: 1.35rem; cursor: pointer; }
	.lineage-edit-body { min-height: 0; overflow-y: auto; display: grid; gap: 8px; padding: 18px 20px; }
	.lineage-edit-body label { color: var(--fg2); font-size: .78rem; font-weight: 700; }
	.lineage-edit-body textarea { box-sizing: border-box; width: 100%; min-height: 180px; resize: vertical; border: 1px solid var(--border2); border-radius: 8px; padding: 12px 14px; background: var(--bg); color: var(--fg); font: inherit; line-height: 1.65; }
	.lineage-edit-body textarea.ddl-editor { min-height: 390px; tab-size: 2; white-space: pre; font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace; font-size: .82rem; line-height: 1.55; }
	.lineage-edit-dialog > footer { display: flex; justify-content: flex-end; gap: 8px; padding: 12px 20px 16px; border-top: 1px solid var(--border); }
	.lineage-edit-dialog > footer button { border: 1px solid var(--border2); border-radius: 7px; padding: 9px 15px; background: var(--panel); color: var(--fg); cursor: pointer; }
	.lineage-edit-dialog > footer .edit-draw { border-color: var(--accent); background: var(--accent); color: var(--accent-fg, #111); font-weight: 700; }
	.lineage-edit-dialog button:disabled, .lineage-edit-dialog textarea:disabled { opacity: .55; cursor: default; }
	.okugaki-backdrop { position: fixed; inset: 0; z-index: 1450; display: grid; place-items: center; padding: 24px; background: #0009; }
	.okugaki-dialog { box-sizing: border-box; width: min(760px, 96vw); max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 24px 80px #000a; }
	.okugaki-dialog > header { padding: 18px 20px 14px; margin: 0; border-bottom: 1px solid var(--border); }
	.okugaki-dialog > header button, .okugaki-record-head button { border: 0; background: transparent; color: var(--fg3); font-size: 1.2rem; cursor: pointer; }
	.okugaki-controls { display: grid; gap: 10px; padding: 14px 20px; border-bottom: 1px solid var(--border); }
	.okugaki-generate { justify-self: start; border: 1px solid var(--accent); border-radius: 7px; padding: 9px 14px; background: var(--accent); color: var(--accent-fg, #111); cursor: pointer; }
	.okugaki-progress { display: flex; align-items: center; gap: 8px; color: var(--fg2); font-size: .8rem; }
	.okugaki-progress span { width: 13px; height: 13px; border: 2px solid var(--border2); border-top-color: var(--accent); border-radius: 50%; animation: okugaki-spin .8s linear infinite; }
	.okugaki-list { min-height: 160px; overflow-y: auto; padding: 18px 20px 24px; display: grid; gap: 16px; }
	.okugaki-record { border: 1px solid var(--border); border-radius: 9px; padding: 14px 16px; background: var(--bg); }
	.okugaki-record-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; color: var(--fg3); font-size: .72rem; }
	.okugaki-body { white-space: pre-wrap; line-height: 1.85; font-family: serif; font-size: .92rem; }
	.okugaki-warning { margin-top: 10px; color: #b98232; font-size: .72rem; }
	@keyframes okugaki-spin { to { transform: rotate(360deg); } }
	.card-menu-trigger { position: absolute; z-index: 3; top: 0; right: 0; display: grid; place-items: center; width: 22px; height: 22px; border: 0; padding: 0; border-radius: 4px; background: color-mix(in srgb, var(--panel) 88%, transparent); color: var(--fg3); cursor: pointer; }
	.card-menu-trigger:hover { background: var(--bg2); color: var(--fg); }
	.card-dropdown-menu { position: absolute; z-index: 10; top: 27px; right: 0; min-width: 230px; border: 1px solid var(--border2); border-radius: 6px; padding: 5px 0; background: var(--panel); box-shadow: 0 6px 20px rgba(0, 0, 0, 0.35); display: flex; flex-direction: column; }
	.card-dropdown-menu button { border: 0; background: transparent; color: var(--fg); padding: 10px 13px; font-size: 0.84rem; line-height: 1.35; text-align: left; cursor: pointer; font-family: inherit; width: 100%; box-sizing: border-box; }
	.card-dropdown-menu button:hover { background: var(--bg2); }
	.card-main { display: block; width: 100%; min-width: 0; border: 0; padding: 0; background: transparent; color: inherit; cursor: pointer; text-align: left; font: inherit; }
	.card-main:disabled { cursor: default; }
	.card-main:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 6px; }
	.operation { min-height: 18px; margin-bottom: 6px; color: var(--fg2); font-size: .7rem; }
	.identity-marks { min-width: 0; display: flex; flex-wrap: wrap; justify-content: flex-start; gap: 3px; }
	.identity-mark, .active-mark { border-radius: 999px; padding: 1px 5px; font-size: .62rem; }
	.identity-mark { color: var(--fg3); background: var(--bg2); }
	.active-mark { color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, var(--panel)); font-weight: 700; }
	.preview { width: 100%; height: 118px; border-radius: 6px; overflow: hidden; background: var(--bg2); }
	.preview :global(.history-thumbnail) { width: 100%; height: 100%; aspect-ratio: auto; }
	.preview :global(svg) { width: 100%; height: 100%; display: block; }
	.preview span { height: 100%; display: grid; place-items: center; color: var(--fg3); }
	.trash-state { margin-top: 6px; color: var(--fg3); font-size: .64rem; }
	.display-label { margin-top: 7px; color: var(--fg3); font-size: .65rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.meta { margin-top: 4px; min-width: 0; height: 2.7em; overflow: hidden; font-size: .72rem; line-height: 1.35; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; }
	.branch-toggle { width: 100%; margin-top: 7px; padding: 5px; font-size: .68rem; }
	.node-details { margin-top: 7px; font-size: .66rem; }
	.node-details summary { cursor: pointer; color: var(--fg3); }
	.node-details dl { display: grid; grid-template-columns: auto 1fr; gap: 2px 6px; margin: 6px 0 0; }
	.node-details dt { color: var(--fg3); }
	.node-details dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
	.full-source { max-height: 7em; overflow: auto; white-space: pre-wrap; }
	.note-editor { display: grid; gap: 5px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
	.note-editor label { color: var(--fg3); }
	.note-editor textarea { box-sizing: border-box; width: 100%; min-height: 4.5em; resize: vertical; border: 1px solid var(--border2); border-radius: 5px; padding: 5px 6px; background: var(--bg); color: var(--fg); font: inherit; line-height: 1.35; }
	.note-editor button { justify-self: end; border: 1px solid var(--border2); border-radius: 5px; padding: 4px 9px; background: var(--panel); color: var(--fg); cursor: pointer; }
	.note-editor button:disabled { opacity: .45; cursor: default; }
	.promote { width: 100%; margin-top: 7px; font-size: .68rem; }
	.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
