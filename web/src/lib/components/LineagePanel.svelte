<script lang="ts">
	import { hashDigest, hashSchemeLabel } from '$lib/hashIdentity';
	import { onMount, tick, untrack } from 'svelte';
	import type { HistoryItem } from '$lib/historyManagerState.svelte';
	import HistoryThumbnail from './HistoryThumbnail.svelte';
	import SavedWorkExportMenu from './SavedWorkExportMenu.svelte';
	import WorkEditDialog from './WorkEditDialog.svelte';
	import type { SketchMode } from '$lib/sketch';
	import { derivationKindLabel } from '$lib/derivation';
	import { t } from '$lib/i18n/index.svelte';
	import { groupDigits } from '$lib/formatNumber';
	import { modelDisplayName, modelShortName, qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
	import ModelCardPicker from './ModelCardPicker.svelte';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { SheetVariant } from '$lib/contactSheet';
	import type { SvgProfile } from '$lib/features/export/download';
	import type { SavedWorkExportScope, SavedWorkExportSnapshot } from '$lib/features/export/saved-work';
	import type { LineageGraph, LineageNode } from '$lib/features/history/types';
	import type { LineageBrowsingState, LineageOrientation } from '$lib/features/history/lineage-state.svelte';
	import WorkActionMenu, { type WorkAction } from './WorkActionMenu.svelte';
	export type OkugakiItem = { id?: string; target_node_id: string; branch_snapshot: string[]; model: string; at: number; language: 'ja' | 'en'; body: string; warnings: string[] };

	type Props = {
		graph: LineageGraph | null;
		loading: boolean;
		error: string | null;
		isJapanese: boolean;
		onOpenNode: (node: LineageNode) => void | Promise<void>;
		onOpenNodeInCanvas: (node: LineageNode) => void | Promise<void>;
		onToggleStar: (node: LineageNode, event?: Event) => void | Promise<void>;
		onToggleForRevision: (node: LineageNode, event?: Event) => void | Promise<void>;
		onOpenRefinement: (node: LineageNode, view: 'adjust' | 'compare') => void | Promise<void>;
		onDrawDescription: (node: LineageNode, text: string, signal?: AbortSignal, wild?: boolean | null) => void | Promise<void>;
		onOpenDdlEditor: (node: LineageNode) => void;
		stageLabel: string;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		runTokensIn: number | null;
		runTokensOut: number | null;
		onSaveOkugakiModel: (provider: Provider, model: string) => void | Promise<void>;
		onPromoteNode: (node: LineageNode) => void | Promise<void>;
		onSaveNote: (node: LineageNode, note: string) => void | Promise<void>;
		onAskTrash: (historyIds: string[]) => void;
		onDetach: () => void;
		onLoadOverview: () => void | Promise<void>;
		onLoadBranch: (nodeId: string) => void | Promise<void>;
		onPaintOne: (text: string, options: any) => Promise<any>;
		/** Redraw a work with the sketch off or on, as its child. */
		onDrawSketchGrain: (node: LineageNode, mode: SketchMode, signal?: AbortSignal) => Promise<void>;
		onVisionAdvice: (historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) => Promise<any>;
		onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
		visionModel: string;
		okugakiModel: string;
		visionProviderGroups: ProviderGroup[];
		animationExportSettings: AnimationExportSettings;
		pngTemplates?: ExportTemplate[];
		onDownloadSavedWorkSVG?: (profile: SvgProfile, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkPNG?: (height: number, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkCard?: (historyId: string, snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkDdl?: (snapshot: SavedWorkExportSnapshot) => void | Promise<void>;
		onDownloadSavedWorkAnimation: (snapshot: SavedWorkExportSnapshot, settings: AnimationExportSettings, directory?: FileSystemDirectoryHandle) => void | Promise<void>;
		onDownloadSavedWorkContactSheet: (snapshot: SavedWorkExportSnapshot, variant: SheetVariant) => void | Promise<void>;
		onValidateSavedWorkExport: (snapshot: SavedWorkExportSnapshot) => boolean | Promise<boolean>;
		browsingState: LineageBrowsingState;
	};
	function withheldLabel(node: LineageNode): string | null {
		if (node.redacted === 'not_permitted') return isJapanese ? '非公開' : 'Private';
		if (node.redacted === 'deleted' || node.state === 'tombstone') return isJapanese ? '削除済み' : 'Deleted';
		return null;
	}

	function withheldWorkLabel(node: LineageNode): string {
		if (node.redacted === 'not_permitted') return isJapanese ? '非公開の作品' : 'Private work';
		return isJapanese ? '削除された作品' : 'Deleted work';
	}

	type ArrowPath = { id: string; path: string; tombstone: boolean };
	let { graph, loading, error, isJapanese, onOpenNode, onOpenNodeInCanvas, onToggleStar, onToggleForRevision, onOpenRefinement, onDrawDescription, onOpenDdlEditor, onDrawSketchGrain, stageLabel, stage1ModelLabel, stage2ModelLabel, runTokensIn, runTokensOut, onSaveOkugakiModel, onPromoteNode, onSaveNote, onAskTrash, onDetach, onLoadOverview, onLoadBranch, onPaintOne, onVisionAdvice, onSaveVisionModel, visionModel, okugakiModel, visionProviderGroups, animationExportSettings, pngTemplates = [], onDownloadSavedWorkSVG, onDownloadSavedWorkPNG, onDownloadSavedWorkCard, onDownloadSavedWorkDdl, onDownloadSavedWorkAnimation, onDownloadSavedWorkContactSheet, onValidateSavedWorkExport, browsingState }: Props = $props();

	let lineageColumnsEl = $state<HTMLDivElement | null>(null);
	let lineageScrollEl = $state<HTMLDivElement | null>(null);
	let resizeObserver: ResizeObserver | null = null;
	let arrowFrame: number | null = null;
	let arrowPaths = $state<ArrowPath[]>([]);
	let checkedHistoryIds = $state<string[]>([]);
	let noteDrafts = $state<Record<string, string>>({});
	let savingNoteIds = $state<string[]>([]);
	let overviewLoading = $state(false);
	let lineagePanning = $state(false);
	let panSession: { pointerId: number; x: number; y: number; scrollLeft: number; scrollTop: number } | null = null;
	let activeMenuNodeId = $state<string | null>(null);
	let headerWorkMenuOpen = $state(false);
	let activeAIRefineNode = $state<LineageNode | null>(null);
	let activeEditNode = $state<LineageNode | null>(null);
	// Sketch from life (Stage 0.5): the grain lives on the edit shelf beside
	// description and the instructions -- not on the refinement radio, because
	// changing it re-runs 0.5 and Stage 1 and is not deterministic.
	let activeSketchNode = $state<LineageNode | null>(null);
	let okugakiOpen = $state(false);
	let selectedOkugakiModel = $state('');
	let okugakiItems = $state<OkugakiItem[]>([]);
	let okugakiLoading = $state(false);
	let okugakiGenerating = $state(false);
	let okugakiError = $state<string | null>(null);
	let okugakiLoadedTarget = $state<string | null>(null);
	let detailsNodeId = $state<string | null>(null);
	let detailsDialogEl: HTMLDialogElement | null = $state(null);
	let detailsReturnButton: HTMLButtonElement | null = null;
	const cardElements = new Map<string, HTMLElement>();

	const nodeById = $derived(new Map((graph?.nodes ?? []).map((node) => [node.id, node])));
	const detailsNode = $derived(detailsNodeId ? nodeById.get(detailsNodeId) ?? null : null);
	const focusNode = $derived(graph?.nodes.find((node) => node.id === graph.focus_node_id) ?? null);
	const edgeByChild = $derived(new Map((graph?.edges ?? []).map((edge) => [edge.child_node_id, edge])));
	const focusAnimationHistoryIds = $derived.by(() => {
		const ids: string[] = [];
		const seen = new Set<string>();
		let current = graph?.focus_node_id ?? null;
		while (current && !seen.has(current)) {
			seen.add(current);
			const node = nodeById.get(current);
			if (node?.history?.id) ids.unshift(node.history.id);
			current = edgeByChild.get(current)?.parent_node_id ?? null;
		}
		return ids;
	});
	const focusExportScope = $derived.by((): SavedWorkExportScope | null => {
		const history = focusNode?.history;
		if (!history?.id) return null;
		return { kind: 'current', works: [{ id: history.id, at: history.at, preview: history.svg ?? null, description: history.source_text ?? history.input ?? null, trashed: history.trashed }] };
	});
	const pathExportScope = $derived.by((): SavedWorkExportScope | null => {
		const works = focusAnimationHistoryIds.flatMap((id) => {
			const history = graph?.nodes.find((node) => node.history?.id === id)?.history;
			return history?.id ? [{ id: history.id, at: history.at, preview: history.svg ?? null, description: history.source_text ?? history.input ?? null, trashed: history.trashed }] : [];
		});
		return works.length > 0 ? { kind: 'lineage-path', works } : null;
	});
	const selectionExportScope = $derived.by((): SavedWorkExportScope | null => {
		const works = (graph?.nodes ?? []).flatMap((node) => {
			const history = node.history;
			return history?.id && checkedHistoryIds.includes(history.id)
				? [{ id: history.id, at: history.at, preview: history.svg ?? null, description: history.source_text ?? history.input ?? null, trashed: history.trashed }]
				: [];
		});
		return works.length > 0 ? { kind: 'selection', works } : null;
	});
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
	// Every edge on a root-to-star path. A starred work is a destination, so the
	// route that produced it is drawn in orange all the way back to the origin.
	const starPathEdgeIds = $derived.by(() => {
		const ids = new Set<string>();
		for (const node of graph?.nodes ?? []) {
			if (!node.history?.starred) continue;
			let current: string | null = node.id;
			const seen = new Set<string>();
			while (current && !seen.has(current)) {
				seen.add(current);
				const edge = edgeByChild.get(current);
				if (!edge) break;
				ids.add(edge.id);
				current = edge.parent_node_id;
			}
		}
		return ids;
	});
	const visibleNodeIds = $derived.by(() => {
		if (browsingState.overviewOpen) return new Set((graph?.nodes ?? []).map((node) => node.id));
		const visible = new Set(ancestorIds);
		const queue = [...ancestorIds];
		const expanded = new Set(browsingState.expandedNodeIds);
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


	// The details show only a suffix; each button copies its complete digest.
	let copiedHashKey = $state<string | null>(null);
	let copiedHashTimer: ReturnType<typeof setTimeout> | null = null;

	function hashSuffix(value: string | null | undefined): string {
		const digest = hashDigest(value);
		return digest ? `…${digest.slice(-4)}` : '—';
	}

	function openNodeDetails(node: LineageNode, event: MouseEvent): void {
		detailsReturnButton = event.currentTarget as HTMLButtonElement;
		detailsNodeId = node.id;
		void tick().then(() => {
			if (detailsDialogEl && !detailsDialogEl.open) detailsDialogEl.showModal();
		});
	}

	function closeNodeDetails(): void {
		detailsDialogEl?.close();
	}

	function handleNodeDetailsClose(): void {
		detailsNodeId = null;
		detailsReturnButton?.focus();
		detailsReturnButton = null;
	}

	function copyNodeHash(node: LineageNode, kind: 'description' | 'render', event: MouseEvent): void {
		event.stopPropagation();
		event.preventDefault();
		const value = kind === 'description' ? node.description_hash : node.render_hash;
		if (!value) return;
		const hash = hashDigest(value);
		if (navigator.clipboard?.writeText) {
			void navigator.clipboard.writeText(hash).catch(() => fallbackCopy(hash));
		} else {
			fallbackCopy(hash);
		}
		copiedHashKey = `${node.id}:${kind}`;
		if (copiedHashTimer) clearTimeout(copiedHashTimer);
		copiedHashTimer = setTimeout(() => (copiedHashKey = null), 1400);
	}

	function fallbackCopy(text: string): void {
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

	// Same shape the canvas provenance uses: the engine id and its version share a
	// line. Works recorded before the field existed carry neither, and an em dash
	// says that more quietly than a bare slash.
	function operationLabel(kind?: string): string {
		return derivationKindLabel(kind, isJapanese);
	}

// The short name is for the card; the full "provider / model" stays in the
// title, so the provider is one hover away rather than gone.
function stageModelNames(history: HistoryItem | null | undefined): string {
	const stage1 = modelShortName(history?.stage1_model);
	const stage2 = modelShortName(history?.stage2_model);
	if (!stage1 && !stage2) return '';
	if (stage1 && stage2 && stage1 !== stage2) return `${stage1} / ${stage2}`;
	return stage1 || stage2;
}

function stageModelTitle(history: HistoryItem | null | undefined): string {
	const stage1 = history?.stage1_model ? modelDisplayName(history.stage1_model) : '';
	const stage2 = history?.stage2_model ? modelDisplayName(history.stage2_model) : '';
	return [stage1 && `Stage 1: ${stage1}`, stage2 && `Stage 2: ${stage2}`].filter(Boolean).join('\n');
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
		// Do not reload the selected work; a double-click must not fetch twice.
		if (node.id === graph?.focus_node_id) return;
		await onOpenNode(node);
	}

	async function loadOkugaki(force = false): Promise<void> {
		const nodeId = graph?.focus_node_id;
		if (!nodeId || (!force && okugakiLoadedTarget === nodeId)) return;
		okugakiLoading = true;
		okugakiError = null;
		try {
			const response = await fetch(`/api/lineage/${encodeURIComponent(nodeId)}/colophon`, { credentials: 'include', cache: 'no-store' });
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
			const response = await fetch(`/api/lineage/${encodeURIComponent(nodeId)}/colophon`, {
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
		const response = await fetch(`/api/colophon/${encodeURIComponent(item.id)}`, { method: 'DELETE', credentials: 'include' });
		if (response.ok) okugakiItems = okugakiItems.filter((entry) => entry.id !== item.id);
		else okugakiError = (await response.text()) || `HTTP ${response.status}`;
	}

	function openEditDialog(node: LineageNode): void {
		if (!node.history) return;
		activeEditNode = node;
		activeMenuNodeId = null;
	}

	function openSketchDialog(node: LineageNode): void {
		if (!node.history) return;
		activeSketchNode = node;
		activeMenuNodeId = null;
	}

	async function runWorkAction(action: WorkAction, node: LineageNode): Promise<void> {
		switch (action) {
			case 'adjust': await onOpenRefinement(node, 'adjust'); break;
			case 'description': openEditDialog(node); break;
			case 'instructions': onOpenDdlEditor(node); break;
			case 'sketch-grain': openSketchDialog(node); break;
			case 'models': await onOpenRefinement(node, 'compare'); break;
			case 'autonomous': activeAIRefineNode = node; break;
		}
	}


	async function selectOkugakiModel(provider: Provider, model: string): Promise<void> {
		const nextModel = qualifiedModelId(provider, model);
		const previous = selectedOkugakiModel;
		selectedOkugakiModel = nextModel;
		okugakiError = null;
		try {
			await onSaveOkugakiModel(provider, model);
		} catch (cause) {
			selectedOkugakiModel = previous;
			okugakiError = cause instanceof Error ? cause.message : String(cause);
		}
	}


	async function toggleBranch(node: LineageNode): Promise<void> {
		if (browsingState.expandedNodeIds.includes(node.id)) {
			browsingState.expandedNodeIds = browsingState.expandedNodeIds.filter((id) => id !== node.id);
			return;
		}
		const loadedCount = childrenByParent.get(node.id)?.length ?? 0;
		const needsLoad = (node.child_count ?? loadedCount) > loadedCount;
		// Loading children flips `loading`, which unmounts the scroll area and would
		// reset scrollTop to 0. Preserve and restore the scroll position across it.
		rememberScroll();
		if (needsLoad) await onLoadBranch(node.id);
		browsingState.expandedNodeIds = [...browsingState.expandedNodeIds, node.id];
		if (needsLoad) {
			await tick();
			restoreScroll();
		}
	}
	function setLineageOrientation(next: LineageOrientation): void {
		if (next === browsingState.orientation) return;
		browsingState.orientation = next;
		void tick().then(() => {
			scheduleArrowUpdate();
			restoreScroll();
		});
	}

	async function openOverview(): Promise<void> {
		rememberScroll();
		browsingState.overviewOpen = true;
		overviewLoading = true;
		try { await onLoadOverview(); }
		finally { overviewLoading = false; await tick(); restoreScroll(); scheduleArrowUpdate(); }
	}
	function closeOverview(): void {
		rememberScroll();
		browsingState.overviewOpen = false;
		void tick().then(() => { restoreScroll(); scheduleArrowUpdate(); });
	}
	function rememberScroll(): void {
		if (!lineageScrollEl) return;
		browsingState.setScroll(browsingState.overviewOpen, {
			left: lineageScrollEl.scrollLeft,
			top: lineageScrollEl.scrollTop,
		});
	}
	function restoreScroll(): void {
		if (!lineageScrollEl) return;
		const position = browsingState.scrollFor(browsingState.overviewOpen);
		lineageScrollEl.scrollLeft = position.left;
		lineageScrollEl.scrollTop = position.top;
	}
	function handleLineageScroll(): void { rememberScroll(); }
	function startLineagePan(event: PointerEvent): void {
		if (event.pointerType !== 'mouse' || event.button !== 0 || !event.isPrimary) return;
		const target = event.target;
		if (!(target instanceof Element) || target.closest('.lineage-card, button, input, textarea, select, label, a, summary, [role="menuitem"]')) return;
		const scroll = event.currentTarget as HTMLDivElement;
		panSession = {
			pointerId: event.pointerId,
			x: event.clientX,
			y: event.clientY,
			scrollLeft: scroll.scrollLeft,
			scrollTop: scroll.scrollTop,
		};
		lineagePanning = true;
		scroll.setPointerCapture(event.pointerId);
		event.preventDefault();
	}
	function moveLineagePan(event: PointerEvent): void {
		if (!panSession || event.pointerId !== panSession.pointerId) return;
		const scroll = event.currentTarget as HTMLDivElement;
		scroll.scrollLeft = panSession.scrollLeft - (event.clientX - panSession.x);
		scroll.scrollTop = panSession.scrollTop - (event.clientY - panSession.y);
		event.preventDefault();
	}
	function endLineagePan(event: PointerEvent): void {
		if (!panSession || event.pointerId !== panSession.pointerId) return;
		const scroll = event.currentTarget as HTMLDivElement;
		panSession = null;
		lineagePanning = false;
		if (scroll.hasPointerCapture(event.pointerId)) scroll.releasePointerCapture(event.pointerId);
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
			let path: string;
			if (browsingState.orientation === 'horizontal') {
				const x1 = parentRect.left + parentRect.width + 1;
				const y1 = parentRect.top + parentRect.height / 2;
				const x2 = childRect.left - 7;
				const y2 = childRect.top + childRect.height / 2;
				const bend = Math.max(18, (x2 - x1) / 2);
				path = `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`;
			} else {
				const x1 = parentRect.left + parentRect.width / 2;
				const y1 = parentRect.top + parentRect.height + 1;
				const x2 = childRect.left + childRect.width / 2;
				const y2 = childRect.top - 7;
				const bend = Math.max(18, (y2 - y1) / 2);
				path = `M ${x1} ${y1} C ${x1} ${y1 + bend}, ${x2} ${y2 - bend}, ${x2} ${y2}`;
			}
			return [{
				id: edge.id,
				path,
				tombstone: [nodeById.get(edge.parent_node_id), nodeById.get(edge.child_node_id)]
					.some((n) => n?.state === 'tombstone' || n?.redacted === 'not_permitted'),
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
			if (copiedHashTimer !== null) clearTimeout(copiedHashTimer);
			resizeObserver?.disconnect();
			resizeObserver = null;
			window.removeEventListener('resize', scheduleArrowUpdate);
			window.removeEventListener('click', handleGlobalClick);
			if (arrowFrame !== null) window.cancelAnimationFrame(arrowFrame);
		};
	});

	$effect(() => {
		const nextGraph = graph;
		const focusId = nextGraph?.focus_node_id ?? null;
		const treeChanged = untrack(() => browsingState.reconcileGraph(nextGraph));
		void tick().then(() => {
			scheduleArrowUpdate();
			untrack(restoreScroll);
			if (treeChanged && focusId && !browsingState.overviewOpen) cardElements.get(focusId)?.scrollIntoView({ block: 'center', inline: 'center' });
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

<section class="lineage-panel" class:overview={browsingState.overviewOpen}>
	<header>
		<div>
			<h2 id="lineage-title">{isJapanese ? '作品の系譜' : 'Lineage of the work'}</h2>
			{#if browsingState.overviewOpen}<p>{browsingState.orientation === 'horizontal' ? (isJapanese ? '全体を左から右へ見渡せます。' : 'Review the complete tree from left to right.') : (isJapanese ? '全体を上から下へ見渡せます。' : 'Review the complete tree from top to bottom.')}</p>{/if}
		</div>
		<div class="lineage-actions">
			<div class="toolbar-group" aria-label={t().lineageViewTools}>
				<span class="toolbar-label">{t().lineageViewTools}</span>
				<div class="orientation-toggle" role="group" aria-label={isJapanese ? '系譜の方向' : 'Lineage direction'}>
					<button type="button" class:active={browsingState.orientation === 'vertical'} aria-pressed={browsingState.orientation === 'vertical'} onclick={() => setLineageOrientation('vertical')}>{isJapanese ? '縦' : 'Vertical'}</button>
					<button type="button" class:active={browsingState.orientation === 'horizontal'} aria-pressed={browsingState.orientation === 'horizontal'} onclick={() => setLineageOrientation('horizontal')}>{isJapanese ? '横' : 'Horizontal'}</button>
				</div>
				{#if browsingState.overviewOpen}
					<div class="overview-zoom"><button type="button" onclick={() => (browsingState.overviewScale = Math.max(.4, browsingState.overviewScale - .1))}>−</button><span>{Math.round(browsingState.overviewScale * 100)}%</span><button type="button" onclick={() => (browsingState.overviewScale = Math.min(1.4, browsingState.overviewScale + .1))}>＋</button></div>
					<button type="button" onclick={closeOverview}>{isJapanese ? '全体図を閉じる' : 'Close map'}</button>
				{:else}
					<button type="button" onclick={openOverview}>{isJapanese ? '全体図' : 'Map'}</button>
				{/if}
			</div>

			<div class="toolbar-group" aria-label={t().lineageFocusedWork}>
				<span class="toolbar-label">{t().lineageFocusedWork}</span>
				<WorkActionMenu
					node={focusNode}
					{isJapanese}
					variant="header"
					open={headerWorkMenuOpen}
					onOpenChange={(open) => (headerWorkMenuOpen = open)}
					onAction={runWorkAction}
				/>
				<button type="button" disabled={!focusNode?.history} onclick={() => focusNode && void onOpenNodeInCanvas(focusNode)}>{t().lineageOpenLarge}</button>
				<SavedWorkExportMenu
					scope={focusExportScope}
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
			</div>

			<div class="toolbar-group" aria-label={t().lineagePathScope(focusAnimationHistoryIds.length)}>
				<span class="toolbar-label">{t().lineagePathScope(focusAnimationHistoryIds.length)}</span>
				<SavedWorkExportMenu
					scope={pathExportScope}
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
			</div>

			<div class="toolbar-group" aria-label={t().lineageSelectionActions}>
				<span class="toolbar-label">{t().lineageSelectionScope(checkedHistoryIds.length)}</span>
				<SavedWorkExportMenu
					scope={selectionExportScope}
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
				<button class="bulk-trash" type="button" disabled={checkedHistoryIds.length === 0} title={isJapanese ? 'チェックした作品をゴミ箱へ移動' : 'Move checked works to trash'} aria-label={isJapanese ? 'チェックした作品をゴミ箱へ移動' : 'Move checked works to trash'} onclick={askTrashChecked}>
					<svg viewBox="2 2 20 20" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M6 6l1 15h10l1-15"></path><path d="M10 10v7"></path><path d="M14 10v7"></path></svg>
				</button>
			</div>

			<div class="toolbar-group lineage-history-tools">
				<button type="button" disabled={!graph?.focus_node_id} title={t().okugakiTooltip} onclick={() => { selectedOkugakiModel = okugakiModel || visionModel; okugakiOpen = true; void loadOkugaki(true); }}>{t().okugakiRead}</button>
				<button type="button" class="detach-btn" onclick={onDetach}>{isJapanese ? '新しい起点にする' : 'Start a new root'}</button>
			</div>
		</div>
	</header>
	{#if loading || overviewLoading}
		<div class="lineage-message">{isJapanese ? '系譜を読み込み中…' : 'Loading lineage…'}</div>
	{:else if error}
		<div class="lineage-message error">{error}</div>
	{:else if !graph || graph.nodes.length === 0}
		<div class="lineage-message">{isJapanese ? '保存すると、ここに系譜が表示されます。' : 'Save a work to begin its lineage.'}</div>
	{:else}
		<div
			class="lineage-scroll"
			role="region"
			aria-labelledby="lineage-title"
			class:overview-scroll={browsingState.overviewOpen}
			class:horizontal={browsingState.orientation === 'horizontal'}
			class:panning={lineagePanning}
			bind:this={lineageScrollEl}
			onscroll={handleLineageScroll}
			onpointerdown={startLineagePan}
			onpointermove={moveLineagePan}
			onpointerup={endLineagePan}
			onpointercancel={endLineagePan}
			onlostpointercapture={endLineagePan}
		>
			<div class="lineage-columns" class:horizontal={browsingState.orientation === 'horizontal'} bind:this={lineageColumnsEl} style={browsingState.overviewOpen ? (browsingState.orientation === 'horizontal' ? `transform: scale(${browsingState.overviewScale}); transform-origin: top left;` : `transform: scale(${browsingState.overviewScale}); transform-origin: top left; width: ${100 / browsingState.overviewScale}%; height: ${100 / browsingState.overviewScale}%;`) : undefined}>
				<svg class="lineage-arrows" aria-hidden="true">
					<defs>
						<marker id="lineage-arrowhead" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth">
							<path d="M 0 0 L 7 3.5 L 0 7 z"></path>
						</marker>
						<marker id="lineage-arrowhead-star" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth">
							<path class="star-head" d="M 0 0 L 7 3.5 L 0 7 z"></path>
						</marker>
					</defs>
					{#each arrowPaths as arrow (arrow.id)}
						{@const onStarPath = starPathEdgeIds.has(arrow.id)}
						<path class="lineage-arrow" class:tombstone-arrow={arrow.tombstone} class:star-arrow={onStarPath} d={arrow.path} marker-end={onStarPath ? 'url(#lineage-arrowhead-star)' : 'url(#lineage-arrowhead)'}></path>
					{/each}
				</svg>
				{#each columns as [depth, nodes] (depth)}
					<div class="lineage-column" class:menu-layer={nodes.some((node) => node.id === activeMenuNodeId)}>
						<div class="generation">{isJapanese ? `第${depth + 1}世代` : `Generation ${depth + 1}`}</div>
						{#each nodes as node (node.id)}
							{@const edge = edgeByChild.get(node.id)}
							{@const childCount = node.child_count ?? childrenByParent.get(node.id)?.length ?? 0}
							<article use:registerCard={node.id} class="lineage-card" class:focus={node.id === graph.focus_node_id} class:tombstone={node.state === 'tombstone' || node.redacted === 'not_permitted'} class:trashed={!!node.history?.trashed} class:menu-open={node.id === activeMenuNodeId}>
<div class="card-toolbar">
{#if node.history?.id && !node.history.trashed}
	<label class="card-check" aria-label={isJapanese ? '一括操作の対象にする' : 'Check for bulk actions'}>
		<input type="checkbox" checked={checkedHistoryIds.includes(node.history.id)} onclick={(event) => event.stopPropagation()} onpointerdown={(event) => event.stopPropagation()} onchange={() => toggleCheckedHistory(node.history?.id as string)} />
	</label>
	{/if}
	{#if node.history?.id}
		<button
			type="button"
			class="card-star"
			class:starred={!!node.history.starred}
			title={node.history.starred ? t().starOn : t().starOff}
			aria-label={node.history.starred ? t().starOn : t().starOff}
			aria-pressed={!!node.history.starred}
			onpointerdown={(event) => event.stopPropagation()}
			onclick={(event) => { event.stopPropagation(); void onToggleStar(node, event); }}
		>★</button>
		<button
			type="button"
			class="card-mark"
			class:marked={!!node.history.for_revision}
			title={node.history.for_revision ? t().forRevisionOn : t().forRevisionOff}
			aria-label={node.history.for_revision ? t().forRevisionOn : t().forRevisionOff}
			aria-pressed={!!node.history.for_revision}
			onpointerdown={(event) => event.stopPropagation()}
			onclick={(event) => { event.stopPropagation(); void onToggleForRevision(node, event); }}
		>⚑</button>
	{/if}
	<span class="identity-marks">
		{#if node.id === graph.focus_node_id}<span class="active-mark">{isJapanese ? '表示中' : 'Displayed'}</span>{/if}
		{#if node.state === 'lineage_only'}<span class="identity-mark">{isJapanese ? '中間作品・履歴非表示' : 'Intermediate · hidden from history'}</span>{/if}
		{#if node.id !== graph.focus_node_id && node.description_hash && node.description_hash === focusNode?.description_hash}<span class="identity-mark">{isJapanese ? '同じ記述' : 'Same text'}</span>{/if}
		{#if node.id !== graph.focus_node_id && node.render_hash && node.render_hash === focusNode?.render_hash}<span class="identity-mark">{isJapanese ? '同じ版' : 'Same edition'}</span>{/if}
	</span>
{#if node.history?.id && !node.history.trashed}
	<WorkActionMenu
		{node}
		{isJapanese}
		variant="card"
		open={activeMenuNodeId === node.id}
		onOpenChange={(open) => (activeMenuNodeId = open ? node.id : null)}
		onAction={runWorkAction}
	/>
{/if}
</div>

								<button type="button" class="card-main" disabled={!node.history} aria-current={node.id === graph.focus_node_id ? 'true' : undefined} aria-label={node.history ? `${operationLabel(edge?.derivation_kind)}: ${node.history.source_text ?? node.history.input}` : withheldWorkLabel(node)} onclick={() => openNode(node)} ondblclick={() => { if (node.history) void onOpenNodeInCanvas(node); }}>
									<div class="operation">
										<span>{operationLabel(edge?.derivation_kind)}</span>
										<!-- Both stages only when they differ: naming the same model twice
										     on a card this narrow says nothing and costs the width the
										     operation label needs. Nothing at all when no model was
										     recorded -- an em dash on every such card fills the lineage
										     with punctuation. -->
										{#if stageModelNames(node.history)}
											<span class="operation-model" title={stageModelTitle(node.history)}>{stageModelNames(node.history)}</span>
										{/if}
									</div>
									<div class="preview">
										{#if node.history?.svg}<HistoryThumbnail item={node.history} scope={`lineage-${node.id}`} size="manager" />{:else}<span>{withheldLabel(node) ?? (isJapanese ? '削除済み' : 'Deleted')}</span>{/if}
									</div>
									{#if node.history?.display_label}<div class="display-label">{node.history.display_label}</div>{/if}
									{#if node.history?.trashed}<div class="trash-state">{isJapanese ? 'ゴミ箱（復元可能）' : 'In trash (restorable)'}</div>{/if}
									<div class="meta" title={node.history?.source_text ?? node.history?.input ?? node.description_hash ?? ''}>{node.history?.source_text || node.history?.input || withheldWorkLabel(node)}</div>
								</button>
								{#if childCount > 0 && !browsingState.overviewOpen}
									<button class="branch-toggle" type="button" aria-expanded={browsingState.expandedNodeIds.includes(node.id)} onclick={() => toggleBranch(node)}>{browsingState.expandedNodeIds.includes(node.id) ? '▾' : '▸'} {isJapanese ? `子作品 ${groupDigits(childCount)}件` : `${groupDigits(childCount)} children`}</button>
								{/if}
								{#if node.history && !browsingState.overviewOpen}
									<button class="node-details-trigger" type="button" onclick={(event) => openNodeDetails(node, event)}>{isJapanese ? '詳細' : 'Details'}</button>
								{/if}
								{#if node.state === 'lineage_only'}<button class="promote" type="button" onclick={() => onPromoteNode(node)}>{isJapanese ? '通常履歴に保存' : 'Save to regular history'}</button>{/if}
							</article>
						{/each}
					</div>
				{/each}
			</div>
		</div>
		<ol class="sr-only" aria-label={isJapanese ? '作品系譜の階層一覧' : 'Lineage hierarchy of works'}>
			{#each graph.nodes as node (node.id)}
				{@const edge = edgeByChild.get(node.id)}
				<li>{node.id === graph.focus_node_id ? (isJapanese ? '表示中 — ' : 'Displayed — ') : ''}{operationLabel(edge?.derivation_kind)} — {node.history?.source_text ?? node.history?.input ?? withheldWorkLabel(node)}</li>
			{/each}
		</ol>
	{/if}
</section>

{#if detailsNode && detailsNode.history}
	{@const detailEdge = edgeByChild.get(detailsNode.id)}
	<dialog bind:this={detailsDialogEl} class="lineage-details-dialog" aria-labelledby="lineage-details-title" onclose={handleNodeDetailsClose}>
		<header>
			<div>
				<h2 id="lineage-details-title">{isJapanese ? '作品の詳細' : 'Work details'}</h2>
				<p>{operationLabel(detailEdge?.derivation_kind)}</p>
			</div>
			<button type="button" class="lineage-details-close" aria-label={isJapanese ? '閉じる' : 'Close'} onclick={closeNodeDetails}>×</button>
		</header>
		<div class="lineage-details-body">
			<dl class="lineage-details-grid">
				<dt class="full-source-label">{isJapanese ? '記述' : 'Text'}</dt><dd class="full-source">{detailsNode.history.source_text ?? detailsNode.history.input}</dd>
				<dt>{hashSchemeLabel(detailsNode.description_hash, 'dh')}</dt>
				<dd class="hash-cell">
					<span>{hashSuffix(detailsNode.description_hash)}</span>
					{#if detailsNode.description_hash}
						<button type="button" class="hash-copy" title={t().historyHashCopyTitle} aria-label={`${hashSchemeLabel(detailsNode.description_hash, 'dh')}: ${t().historyHashCopyTitle}`} onclick={(event) => copyNodeHash(detailsNode, 'description', event)}>
							{copiedHashKey === `${detailsNode.id}:description` ? t().promptCopied : t().promptCopy}
						</button>
					{/if}
				</dd>
				<dt>{hashSchemeLabel(detailsNode.render_hash, 'rh')}</dt>
				<dd class="hash-cell">
					<span>{hashSuffix(detailsNode.render_hash)}</span>
					{#if detailsNode.render_hash}
						<button type="button" class="hash-copy" title={t().historyHashCopyTitle} aria-label={`${hashSchemeLabel(detailsNode.render_hash, 'rh')}: ${t().historyHashCopyTitle}`} onclick={(event) => copyNodeHash(detailsNode, 'render', event)}>
							{copiedHashKey === `${detailsNode.id}:render` ? t().promptCopied : t().promptCopy}
						</button>
					{/if}
				</dd>
				<dt>Render engine version</dt><dd>{detailsNode.history.render_engine_version || '—'}</dd>
				<dt>{t().provenanceLabelTransformLayer}</dt><dd>{detailsNode.history.ddl_engine_version || '—'}</dd>
				<dt>Build</dt><dd>{detailsNode.history.render_build_number || '—'}</dd>
				<dt>Stage 1</dt><dd>{detailsNode.history.stage1_model ? modelDisplayName(detailsNode.history.stage1_model) : '—'}</dd>
				<dt>Stage 2</dt><dd>{detailsNode.history.stage2_model ? modelDisplayName(detailsNode.history.stage2_model) : '—'}</dd>
				<dt>seed</dt><dd>{detailsNode.history.render_seed ?? '—'} / {detailsNode.history.composition_seed ?? '—'} / {detailsNode.history.interpretation_seed ?? '—'}</dd>
				<dt>{isJapanese ? '派生' : 'Derived by'}</dt><dd>{operationLabel(detailEdge?.derivation_kind)}</dd>
			</dl>
			<div class="note-editor">
				<label for={`lineage-note-${detailsNode.id}`}>{isJapanese ? '作品へのコメント' : 'Comment on the work'}</label>
				<textarea id={`lineage-note-${detailsNode.id}`} maxlength="240" rows="3" value={noteValue(detailsNode)} disabled={savingNoteIds.includes(detailsNode.id)} oninput={(event) => updateNoteDraft(detailsNode.id, event.currentTarget.value)}></textarea>
				<button type="button" disabled={savingNoteIds.includes(detailsNode.id) || noteValue(detailsNode).trim() === (detailsNode.history?.note ?? '').trim()} onclick={() => saveNodeNote(detailsNode)}>{savingNoteIds.includes(detailsNode.id) ? (isJapanese ? '保存中…' : 'Saving…') : (isJapanese ? '保存' : 'Save')}</button>
			</div>
		</div>
	</dialog>
{/if}

{#if activeEditNode}
	<WorkEditDialog node={activeEditNode} mode="description" {isJapanese} {stageLabel} {stage1ModelLabel} {stage2ModelLabel} tokensIn={runTokensIn} tokensOut={runTokensOut} onClose={() => (activeEditNode = null)} onDrawDescription={onDrawDescription} {onDrawSketchGrain} />
{/if}

{#if activeSketchNode}
	<WorkEditDialog node={activeSketchNode} mode="sketch-grain" {isJapanese} {stageLabel} {stage1ModelLabel} {stage2ModelLabel} tokensIn={runTokensIn} tokensOut={runTokensOut} onClose={() => (activeSketchNode = null)} onDrawDescription={onDrawDescription} {onDrawSketchGrain} />
{/if}

{#if okugakiOpen}
	<div class="okugaki-backdrop" role="presentation">
		<div class="okugaki-dialog" role="dialog" aria-modal="true" aria-labelledby="okugaki-title" tabindex="-1">
			<header><div><h2 id="okugaki-title">{t().okugakiTitle}</h2><p>{t().okugakiDescription}</p></div><button type="button" disabled={okugakiGenerating} onclick={() => (okugakiOpen = false)}>×</button></header>
			<div class="okugaki-controls">
				<p>{t().okugakiBranchConfirm.replace('{count}', groupDigits(ancestorIds.size))}</p>
				<ModelCardPicker label={t().okugakiModel} selectedModel={selectedOkugakiModel} providerGroups={visionProviderGroups} purpose="vision" disabled={okugakiGenerating} onSelect={(provider: Provider, model: string) => void selectOkugakiModel(provider, model)} />
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
	{#await import('./AIRefineModal.svelte') then { default: AIRefineModal }}
		<AIRefineModal
			node={activeAIRefineNode}
			onClose={() => (activeAIRefineNode = null)}
			{onPaintOne}
			{onVisionAdvice}
			{onSaveVisionModel}
			{visionModel}
			{visionProviderGroups}
			{stage1ModelLabel}
			{stage2ModelLabel}
			onLoadBranch={onLoadBranch}
		/>
	{/await}
{/if}

<style>
	.lineage-panel { box-sizing: border-box; width: 100%; height: 100%; min-width: 0; padding: 22px; overflow: hidden; display: flex; flex-direction: column; color: var(--fg); background: var(--bg); }
	.lineage-panel.overview { position: fixed; inset: 14px; z-index: 1300; width: auto; height: auto; border: 1px solid var(--border2); border-radius: 12px; box-shadow: 0 18px 70px #000a; }
	header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
	h2 { margin: 0 0 4px; font-size: 1.05rem; }
	p { margin: 0; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.lineage-actions, .toolbar-group, .overview-zoom, .orientation-toggle { display: flex; align-items: center; gap: 8px; }
	.lineage-actions { flex-wrap: wrap; justify-content: flex-end; }
	.toolbar-group { flex-wrap: wrap; padding-left: 8px; border-left: 1px solid var(--border); }
	.toolbar-label { color: var(--fg2); font-size: var(--ui-font-size-12); white-space: nowrap; }
	.lineage-history-tools { margin-left: auto; }
	.overview-zoom, .orientation-toggle { padding-right: 8px; border-right: 1px solid var(--border); }
	.orientation-toggle button.active { border-color: var(--accent); background: var(--accent); color: var(--accent-fg); }
	.overview-zoom span { min-width: 42px; color: var(--fg2); font-size: var(--ui-font-size-12); text-align: center; }
	header button, .promote, .branch-toggle { border: 1px solid var(--border2); background: var(--panel); color: var(--fg); border-radius: var(--btn-sm-radius); padding: var(--btn-sm-padding); font-family: inherit; font-size: var(--btn-sm-font-size); cursor: pointer; }
	/* Dimensions follow the header button tokens; only color is overridden here. */
	.detach-btn { background: var(--ddl-btn-bg); border-color: var(--ddl-btn-border); color: var(--ddl-btn-fg); font-weight: 600; box-shadow: var(--ddl-btn-shadow); white-space: nowrap; }
	.detach-btn:hover { background: var(--ddl-btn-bg-hover); border-color: var(--ddl-btn-border-hover); color: var(--ddl-btn-fg-hover); }
	.bulk-trash { min-width: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
	.bulk-trash svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
	.bulk-trash:disabled { opacity: .4; cursor: default; }
	.lineage-message { margin: auto; color: var(--fg2); }
	.lineage-message.error { color: var(--danger, #9b3d32); white-space: pre-line; }
	.lineage-scroll { min-height: 0; overflow-x: hidden; overflow-y: auto; padding: 8px 18px 24px 8px; cursor: grab; }
	.lineage-scroll.horizontal { overflow: auto; }
	.lineage-scroll.panning { cursor: grabbing; user-select: none; }
	.lineage-columns { position: relative; width: 100%; display: flex; flex-direction: column; align-items: stretch; gap: 58px; transform-origin: top center; }
	.lineage-columns.horizontal { width: max-content; min-width: 100%; flex-direction: row; align-items: flex-start; transform-origin: top left; }
	.lineage-arrows { position: absolute; inset: 0; z-index: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
	.lineage-arrow { fill: none; stroke: color-mix(in srgb, var(--fg2) 72%, transparent); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
	.lineage-arrow.tombstone-arrow { stroke-dasharray: 5 4; }
	.lineage-arrows marker path { fill: var(--fg2); }
	/* Root-to-star route. */
	.lineage-arrow.star-arrow { stroke: var(--star-path); stroke-width: 2; }
	.lineage-arrows marker path.star-head { fill: var(--star-path); }
	.lineage-column { position: relative; z-index: 1; width: 100%; min-width: 0; display: flex; flex-wrap: wrap; align-items: flex-start; justify-content: center; gap: 14px 18px; }
	.lineage-columns.horizontal .lineage-column { flex: 0 0 210px; width: 210px; min-width: 210px; flex-direction: column; flex-wrap: nowrap; justify-content: flex-start; gap: 14px; }
	.lineage-column.menu-layer { z-index: 20; }
	.generation { flex: 0 0 100%; color: var(--fg2); font-size: var(--ui-font-size-12); text-align: center; }
	.lineage-columns.horizontal .generation { flex: 0 0 auto; width: 100%; }
	.lineage-card { position: relative; box-sizing: border-box; width: 210px; min-width: 0; max-width: 210px; overflow: hidden; border: 1px solid var(--border); border-radius: 10px; padding: 8px; background: var(--panel); box-shadow: 0 2px 8px color-mix(in srgb, var(--fg) 8%, transparent); cursor: default; }
	.lineage-card.menu-open { z-index: 10; overflow: visible; }
	.lineage-card.focus { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--panel)); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 22%, transparent); }
	.lineage-card.tombstone { border-style: dashed; opacity: .72; }
	.lineage-card.trashed { opacity: .62; filter: grayscale(.35); }
	.card-toolbar { position: relative; z-index: 3; min-height: 22px; margin-bottom: 6px; padding-right: 26px; display: flex; align-items: flex-start; gap: 5px; }
	.card-check { flex: 0 0 auto; display: grid; place-items: center; padding: 2px; border-radius: 4px; background: color-mix(in srgb, var(--panel) 88%, transparent); cursor: pointer; }
	/* Work star: pressing it does not select the work; the card owns selection. */
	.card-star { flex: 0 0 auto; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--border2); border-radius: 50%; padding: 0; background: var(--panel); color: var(--fg2); font-size: var(--ui-font-size-19); line-height: 1; font-family: inherit; cursor: pointer; }
	.card-star.starred { color: var(--star-fg); background: var(--star-bg); border-color: var(--star-border); }
	/* The revision mark rides beside the star in the same shell: the two are
	   separate columns and a work can carry either, both or neither. */
	.card-mark { flex: 0 0 auto; width: 26px; height: 26px; display: inline-flex; align-items: center; justify-content: center; border: 1px solid var(--border2); border-radius: 50%; padding: 0; background: var(--panel); color: var(--fg2); font-size: var(--ui-font-size-16); line-height: 1; font-family: inherit; cursor: pointer; }
	.card-mark.marked { color: var(--danger); background: color-mix(in srgb, var(--danger) 12%, var(--panel)); border-color: color-mix(in srgb, var(--danger) 48%, var(--border2)); }
	.card-check input { width: 15px; height: 15px; margin: 0; accent-color: var(--accent); margin: 0; }
	.okugaki-backdrop { position: fixed; inset: 0; z-index: 1450; display: grid; place-items: center; padding: 24px; background: #0009; }
	.okugaki-dialog { box-sizing: border-box; width: min(760px, 96vw); max-height: 90vh; overflow: hidden; display: flex; flex-direction: column; border: 1px solid var(--border2); border-radius: 12px; background: var(--panel); box-shadow: 0 24px 80px #000a; }
	.okugaki-dialog > header { padding: 18px 20px 14px; margin: 0; border-bottom: 1px solid var(--border); }
	.okugaki-dialog > header button, .okugaki-record-head button { border: 0; background: transparent; color: var(--fg2); font-size: 1.2rem; cursor: pointer; }
	.okugaki-controls { display: grid; gap: 10px; padding: 14px 20px; border-bottom: 1px solid var(--border); }
	.okugaki-generate { justify-self: start; border: 1px solid var(--accent); border-radius: 7px; padding: 9px 14px; background: var(--accent); color: var(--accent-fg); cursor: pointer; }
	.okugaki-progress { display: flex; align-items: center; gap: 8px; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.okugaki-progress span { width: 13px; height: 13px; border: 2px solid var(--border2); border-top-color: var(--accent); border-radius: 50%; animation: okugaki-spin .8s linear infinite; }
	.okugaki-list { min-height: 160px; overflow-y: auto; padding: 18px 20px 24px; display: grid; gap: 16px; }
	.okugaki-record { border: 1px solid var(--border); border-radius: 9px; padding: 14px 16px; background: var(--bg); }
	.okugaki-record-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.okugaki-body { white-space: pre-wrap; line-height: 1.85; font-family: serif; font-size: .92rem; }
	.okugaki-warning { margin-top: 10px; color: #b98232; font-size: var(--ui-font-size-12); }
	@keyframes okugaki-spin { to { transform: rotate(360deg); } }
	.card-main { user-select: none; display: block; width: 100%; min-width: 0; border: 0; padding: 0; background: transparent; color: inherit; cursor: pointer; text-align: left; font: inherit; }
	.card-main:disabled { cursor: default; }
	.card-main:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 6px; }
	/* One line, never wrapping: the card has a fixed width and the operation
	   label sets the row height. The model name gives up its width first and
	   ends in an ellipsis rather than pushing the label onto a second line. */
	.operation { min-height: 18px; margin-bottom: 6px; color: var(--fg2); font-size: var(--ui-font-size-12); display: flex; align-items: baseline; gap: 5px; white-space: nowrap; }
	.operation > span:first-child { flex: 0 0 auto; }
	.operation-model { min-width: 0; overflow: hidden; text-overflow: ellipsis; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.identity-marks { min-width: 0; display: flex; flex-wrap: wrap; justify-content: flex-start; gap: 3px; }
	.identity-mark, .active-mark { border-radius: 999px; padding: 1px 5px; font-size: var(--ui-font-size-12); }
	.identity-mark { color: var(--fg2); background: var(--bg2); }
	.active-mark { color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, var(--panel)); font-weight: 700; }
	.preview { width: 100%; height: 118px; border-radius: 6px; overflow: hidden; background: var(--bg2); }
	.preview :global(.history-thumbnail) { width: 100%; height: 100%; aspect-ratio: auto; }
	.preview :global(svg) { width: 100%; height: 100%; display: block; }
	.preview span { height: 100%; display: grid; place-items: center; color: var(--fg2); }
	.trash-state { margin-top: 6px; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.display-label { margin-top: 7px; color: var(--fg2); font-size: var(--ui-font-size-12); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.meta { margin-top: 4px; min-width: 0; height: 2.7em; overflow: hidden; font-size: var(--ui-font-size-14); line-height: 1.35; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; }
	.branch-toggle { width: 100%; margin-top: 7px; padding: 5px; font-size: var(--ui-font-size-12); }
	.node-details-trigger { width: 100%; margin-top: 7px; border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); padding: 5px 8px; background: var(--bg2); color: var(--fg2); font: inherit; font-size: var(--btn-sm-font-size); text-align: left; cursor: pointer; }
	.node-details-trigger:hover { color: var(--fg); border-color: var(--accent); }
	.node-details-trigger:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
	.lineage-details-dialog { box-sizing: border-box; width: min(640px, calc(100vw - 32px)); max-height: calc(100vh - 32px); margin: auto; border: 1px solid var(--border2); border-radius: 12px; padding: 0; background: var(--panel); color: var(--fg); box-shadow: 0 24px 80px #000a; }
	.lineage-details-dialog[open] { display: flex; flex-direction: column; }
	.lineage-details-dialog::backdrop { background: #0009; }
	.lineage-details-dialog > header { flex: 0 0 auto; display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin: 0; border-bottom: 1px solid var(--border); padding: 18px 20px 14px; }
	.lineage-details-dialog > header h2 { margin: 0 0 4px; font-size: var(--ui-font-size-16); }
	.lineage-details-dialog > header p { margin: 0; color: var(--fg2); font-size: var(--ui-font-size-12); }
	.lineage-details-close { flex: 0 0 auto; border: 0; background: transparent; color: var(--fg2); font-size: var(--ui-font-size-20); cursor: pointer; }
	.lineage-details-body { min-height: 0; overflow-y: auto; padding: 16px 20px 20px; }
	.lineage-details-grid { display: grid; grid-template-columns: 150px minmax(0, 1fr); gap: 8px 16px; margin: 0; font-size: var(--ui-font-size-13); }
	.lineage-details-grid dt { color: var(--fg2); }
	.lineage-details-grid dd { min-width: 0; margin: 0; overflow-wrap: anywhere; line-height: 1.5; }
	.lineage-details-grid dd.hash-cell { display: flex; align-items: center; gap: 10px; }
	.hash-copy { flex: 0 0 auto; border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); padding: 1px 6px; background: var(--panel); color: var(--fg2); font-family: inherit; font-size: inherit; line-height: 1.5; cursor: pointer; }
	.hash-copy:hover { border-color: var(--accent); color: var(--fg); }
	.full-source-label, .full-source { grid-column: 1 / -1; }
	.full-source { max-height: 9em; overflow: auto; white-space: pre-wrap; }
	@media (max-width: 480px) {
		.lineage-details-grid { grid-template-columns: minmax(0, 1fr); gap: 3px; }
		.lineage-details-grid dt:not(:first-child) { margin-top: 8px; }
	}
	.note-editor { display: grid; gap: 5px; margin-top: 8px; padding-top: 8px; border-top: 1px solid var(--border); }
	.note-editor label { color: var(--fg2); }
	.note-editor textarea { box-sizing: border-box; width: 100%; min-height: 4.5em; resize: vertical; border: 1px solid var(--border2); border-radius: 5px; padding: 5px 6px; background: var(--bg); color: var(--fg); font: inherit; line-height: 1.35; }
	.note-editor button { justify-self: end; border: 1px solid var(--border2); border-radius: 5px; padding: 4px 9px; background: var(--panel); color: var(--fg); cursor: pointer; }
	.note-editor button:disabled { opacity: .45; cursor: default; }
	.promote { width: 100%; margin-top: 7px; font-size: var(--ui-font-size-12); }
	.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
