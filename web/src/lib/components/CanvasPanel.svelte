<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { Provider, ProviderGroup } from '$lib/models';
	import CanvasArtworkWorkspace from '$lib/features/canvas/CanvasArtworkWorkspace.svelte';
	import CanvasGenerationInfo from '$lib/features/canvas/CanvasGenerationInfo.svelte';
	import CanvasPresentationOverlay from '$lib/features/canvas/CanvasPresentationOverlay.svelte';
	import CanvasRefinementWorkspace from '$lib/features/canvas/CanvasRefinementWorkspace.svelte';
	import type { LineageGraph, LineageNode, NearbyWork } from '$lib/features/history/types';
	import { measureSvgWeight } from '$lib/svgWeight';
	import { formatCanvasCapacity } from '$lib/formatNumber';
	import { drawerScrollToRestore, emptyDrawerScrollMemory, rememberDrawerScroll, type DrawerTab } from '$lib/drawerScroll';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';

	type ModelInspection = ReturnType<typeof createModelInspection>;
	import Tooltip from './Tooltip.svelte';
	import { composeFallbackReason, composeFallbackState, composeFallbackValue } from '$lib/composeFallback';
	import type { CanvasViewport } from '$lib/features/canvas/viewport-state.svelte';
	import type { PaintResult } from '$lib/features/run/current-work';
	import type { SvgProfile } from '$lib/features/export/download';
	import type { CanvasStatusHistoryItem as HistoryItem } from '$lib/features/canvas/view-types';
	import type {
		RefinementSession,
		RefineKind,
		VariationAmplitude,
		VariationCandidate
	} from '$lib/features/canvas/refinement-session.svelte';

	type OutputTab = 'canvas' | 'refine' | 'lineage';
	type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
	type PromptsData = { stage1_system: string; stage2_system: string };
	type Props = {
		outputTab: OutputTab;
		result: PaintResult | null;
		nearbyHistory: NearbyWork[];
		onOpenNearbyHistory: (id: string) => void;
		unsavedRefinementPreview: boolean;
		lineageIntermediateNotice: string | null;
		allowEmptyOutputTabs: boolean;
		currentRenderedAt: string | null;
		// The three nav buttons, each with its own answer. They come decided by
		// historyNavigation.ts so this panel and the strip read one judgement.
		navLatestDisabled: boolean;
		navNewerDisabled: boolean;
		navOlderDisabled: boolean;
		// A demo is running, so nothing may move. ORed into every nav button
		// below as well: the flags above already carry it, and this is the guard
		// that stays if a caller ever forgets to pass it through them.
		interactionLocked: boolean;
		historyTotal: number;
		navPos: number;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		viewport: CanvasViewport;
		promptsData: PromptsData | null;
		stage1PromptText: string;
		instructionText: string;
		ddl: string | null;
		promptStage1Expanded: boolean;
		promptStage2Expanded: boolean;
		copiedPrompt: 'stage1' | 'stage2' | 'score' | null;
		scoreJsonText: string;
		scoreJsonLines: string[];
		scoreJsonHighlighted: string;
		scoreJsonSeparatorLine: number | null;
		statusStage1Model: string;
		statusStage2Model: string;
		statusStage1ModelOnly: string;
		statusStage2ModelOnly: string;
		visionModel: string;
		okugakiModel: string;
		visionProviderGroups: ProviderGroup[];
		statusCatalogName: string;
		statusCanvasName: string;
		statusGeneration: number | null;
		stageLabel: string;
		statusHistoryItem: HistoryItem | null;
		statusHashLabel: string;
		statusHashCopied: boolean;
		exportMenuOpen: boolean;
		exportWrapEl: HTMLDivElement | null;
		// True when the work tools are hidden. The export button stays on the
		// canvas in that state, but it stops being a door onto three ways out and
		// becomes the one way out a simple UI keeps: the share card. SVG and PNG
		// are work tools; the card is how a work leaves for someone else.
		exportCardOnly: boolean;
		pngTemplates: ExportTemplate[];
		animationExportSettings: AnimationExportSettings;
		apiFetch: ApiFetch;
		// Passed through to LineagePanel for the contact sheet it builds from the
		// checked works; CanvasPanel does not read them itself.
		catalogName: (id: string | null | undefined) => string;
		formatHistoryDate: (at: number) => string;
		historyPreviewText: (text: string) => string;
		onGotoNext: () => void | Promise<void>;
		onGotoPrev: () => void | Promise<void>;
		onGotoLatest: () => void | Promise<void>;
		onCopyPromptText: (kind: 'stage1' | 'stage2' | 'score', text: string | null | undefined) => void | Promise<void>;
		onCopyStatusHash: () => void | Promise<void>;
		onToggleStar: (item: HistoryItem | null | undefined, event?: Event) => void | Promise<void>;
		/** The revision mark of the work on screen, the same flag the history
		    manager's pencil toggles. */
		onToggleForRevision: (item: HistoryItem | null | undefined, event?: Event) => void | Promise<void>;
		/**
		 * The share-target mark. Optional because the flag it stands on does not
		 * exist yet (ledger I-191): this is the socket, and the mark stays off
		 * screen until both the field and this handler arrive. See $lib/shareTarget.
		 */
		onToggleForShare?: ((item: HistoryItem | null | undefined, event?: Event) => void | Promise<void>) | null;
		onReplayCurrent: () => void | Promise<void>;
		replayDisabled: boolean;
		onDownloadSVG: (profile: SvgProfile) => void | Promise<void>;
		onDownloadPNG: (size: number) => void | Promise<void>;
		// The card is built from a saved work, so the toolbar needs its id, not
		// just the drawing on screen.
		currentHistoryId: string | null;
		onDownloadCard: () => void | Promise<void>;
		onVaryPerformance: () => void | Promise<void>;
		onVaryComposition: () => void | Promise<void>;
		onVaryInterpretation: () => void | Promise<void>;
		instructionCaptionVisible: boolean;
		onInstructionCaptionVisibleChange: (visible: boolean) => void | Promise<void>;
		refinementSession: RefinementSession;
		runTokensIn: number | null;
		runTokensOut: number | null;
		/** The whole feature, so a new field costs no line here. */
		modelInspection: ModelInspection;
		touchSeedText: string;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4, touchWords?: string, amplitude?: VariationAmplitude) => void | Promise<void>;
		onSaveSelectedVariationCandidates: () => void | Promise<void>;
		onShowVariationCandidate: (candidate: VariationCandidate) => void;
		activeComparisonItem: { svg: string } | null;
		lineageGraph: LineageGraph | null;
		lineageLoading: boolean;
		lineageError: string | null;
		isJapanese: boolean;
		onOpenLineageNode: (node: LineageNode) => void | Promise<void>;
		onOpenLineageNodeInCanvas: (node: LineageNode) => void | Promise<void>;
		onToggleLineageStar: (node: LineageNode, event?: Event) => void | Promise<void>;
		onToggleLineageForRevision: (node: LineageNode, event?: Event) => void | Promise<void>;
		onDrawLineageDescription: (node: LineageNode, text: string, signal?: AbortSignal) => void | Promise<void>;
		onDrawLineageDdl: (node: LineageNode, ddl: string) => void | Promise<void>;
		onOpenLineageDdlEditor: (node: LineageNode) => void;
		onDrawLineageSketchGrain: (node: LineageNode, grain: 'fine' | 'coarse', signal?: AbortSignal) => Promise<void>;
		onToggleSaijiki: () => void;
		onCloseRefinement: () => void;
		statusDdlOrigin: boolean;
		developerMode: boolean;
		// The staffage level a work was drawn at, for works saved before the axis
		// was folded away (v2.11.0). Developer mode only, and only when set.
		statusTenkei: string | null;
		// The drawing (Stage 2) model, the same one DdlEditorDialog offers and with
		// the same effect: choosing here rewrites the default and persists it.
		refineDrawingModelId: string;
		refineDrawingModelGroups: ProviderGroup[];
		onSelectRefineDrawingModel: (provider: Provider, model: string) => void | Promise<void>;
		refineWildValue: boolean;
		refineWildInherited: boolean;
		onSetRefineWild: (value: boolean | null) => void;
		onSaveOkugakiModel: (provider: Provider, model: string) => void | Promise<void>;
		onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
		onPromoteLineageNode: (node: LineageNode) => void | Promise<void>;
		onSaveLineageNote: (node: LineageNode, note: string) => void | Promise<void>;
		onAskTrashLineage: (historyIds: string[]) => void;
		onDetachLineage: () => void;
		onLoadLineageOverview: () => void | Promise<void>;
		onLoadLineageBranch: (nodeId: string) => void | Promise<void>;
		onPaintOne: (text: string, options: any) => Promise<any>;
		onVisionAdvice: (historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) => Promise<any>;
	};

	let {
		outputTab = $bindable('canvas'),
		result,
		nearbyHistory = [],
		onOpenNearbyHistory,
		unsavedRefinementPreview = false,
		lineageIntermediateNotice = null,
		allowEmptyOutputTabs,
		currentRenderedAt,
		navLatestDisabled,
		navNewerDisabled,
		navOlderDisabled,
		interactionLocked,
		historyTotal,
		navPos,
		canvasAspectWidth = 1,
		canvasAspectHeight = 1,
		viewport,
		promptsData,
		stage1PromptText,
		instructionText,
		ddl,
		promptStage1Expanded = $bindable(false),
		promptStage2Expanded = $bindable(false),
		copiedPrompt,
		scoreJsonText,
		scoreJsonLines,
		scoreJsonHighlighted,
		scoreJsonSeparatorLine,
		statusStage1Model,
		statusStage2Model,
		statusStage1ModelOnly,
		statusStage2ModelOnly,
		visionModel,
		okugakiModel,
		visionProviderGroups,
		statusCatalogName,
		statusCanvasName,
		statusGeneration,
		stageLabel,
		statusHistoryItem,
		statusHashLabel,
		statusHashCopied,
		exportMenuOpen = $bindable(false),
		exportWrapEl = $bindable(null),
		exportCardOnly = false,
		pngTemplates,
		animationExportSettings,
		apiFetch,
		catalogName,
		formatHistoryDate,
		historyPreviewText,
		onGotoNext,
		onGotoPrev,
		onGotoLatest,
		onCopyPromptText,
		onCopyStatusHash,
		onToggleStar,
		onToggleForRevision,
		onToggleForShare = null,
		onReplayCurrent,
		replayDisabled,
		onDownloadSVG,
		onDownloadPNG,
		currentHistoryId,
		onDownloadCard,
		onVaryPerformance,
		onVaryComposition,
		onVaryInterpretation,
		instructionCaptionVisible = $bindable(true),
		onInstructionCaptionVisibleChange,
		refinementSession,
		runTokensIn = null,
		runTokensOut = null,
		modelInspection,
		touchSeedText = $bindable(''),
		onGenerateVariationCandidates,
		onSaveSelectedVariationCandidates,
		onShowVariationCandidate,
		activeComparisonItem,
		lineageGraph = null,
		lineageLoading = false,
		lineageError = null,
		isJapanese = true,
		onOpenLineageNode,
		onOpenLineageNodeInCanvas,
		onToggleLineageStar,
		onToggleLineageForRevision,
		onDrawLineageDescription,
		onDrawLineageDdl,
		onOpenLineageDdlEditor,
		onDrawLineageSketchGrain,
		onToggleSaijiki,
		onCloseRefinement,
		statusDdlOrigin,
		developerMode,
		statusTenkei,
		refineDrawingModelId,
		refineDrawingModelGroups,
		onSelectRefineDrawingModel,
		refineWildValue,
		refineWildInherited,
		onSetRefineWild,
		onSaveOkugakiModel,
		onSaveVisionModel,
		onPromoteLineageNode,
		onSaveLineageNote,
		onAskTrashLineage,
		onDetachLineage,
		onLoadLineageOverview,
		onLoadLineageBranch,
		onPaintOne,
		onVisionAdvice
	}: Props = $props();

	let canvasContentEl = $state<HTMLDivElement | null>(null);

	// The drawing goes on the canvas as an image, not as markup.
	//
	// Measured against production on 2026-08-16: one work was 11,068,576 bytes
	// and 39,789 elements, of which 24,446 carried a filter reference. Put in
	// with {@html} it blocked the main thread for 3,387 ms and left all 39,788
	// nodes in the page, where every later layout and style pass walks them. As
	// an image the browser rasterises it once and the page keeps one node: the
	// same work went from 921 ms blocked and 1,859 ms to paint, down to 681 ms
	// and 17 ms, measured on a blank page at the 784 px the canvas gives it.
	//
	// Safe because the drawing is self-contained -- no currentColor, no CSS
	// variables, no external references, and no style or script element of its
	// own -- so an image cannot lose anything the page was supplying. (Do not
	// write those two tag names out here: the compiler scans this block for
	// them and reads one inside a comment as the real thing.) Nothing reads the
	// artwork's nodes either: zoom and pan are CSS transforms on the boxes
	// around it, svgWeight counts the SVG text, and the PNG and card exports
	// ask the server. The URL is revoked when the work changes, so holding a
	// long session open does not accumulate blobs.
	let artworkUrl = $state<string | null>(null);
	$effect(() => {
		const svg = result?.svg;
		if (!svg) {
			artworkUrl = null;
			return;
		}
		const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
		artworkUrl = url;
		return () => {
			URL.revokeObjectURL(url);
		};
	});

	// The card leaves in one press, so the only state it needs is "in flight".
	let cardExportBusy = $state(false);

	async function downloadCardFromCanvas(): Promise<void> {
		if (cardExportBusy) return;
		cardExportBusy = true;
		try {
			await onDownloadCard();
		} finally {
			cardExportBusy = false;
		}
	}
	let svgHelpOpen = $state(false);
	let presentationMode = $state(false);
	let generationInfoOpen = $state(false);
	let generationInfoTab = $state<DrawerTab>('details');
	let generationInfoEl = $state<HTMLElement | null>(null);
	// The pane that scrolls, which is a different element per tab: the details
	// list is this component's, the other two belong to OutputTabsContent and
	// only one of them exists at a time.
	let detailsScrollEl = $state<HTMLElement | null>(null);
	let tabsScrollEl = $state<HTMLElement | null>(null);
	let drawerScrollMemory = $state(emptyDrawerScrollMemory());
	const drawerScroller = (): HTMLElement | null =>
		generationInfoTab === 'details' ? detailsScrollEl : tabsScrollEl;

	// Every path that closes the drawer goes through here, or the one that does
	// not would be the one that forgets: there are four (the close button, the
	// toggle, Escape, and a press outside).
	function closeGenerationInfo(): void {
		const pane = drawerScroller();
		if (pane) drawerScrollMemory = rememberDrawerScroll(drawerScrollMemory, generationInfoTab, pane.scrollTop);
		generationInfoOpen = false;
	}

	function openGenerationInfo(): void {
		generationInfoOpen = true;
		// After the pane is on screen: the contents may have been rebuilt while
		// the drawer was away, and a scrollTop set against the old height would
		// be clamped to it.
		void tick().then(() => {
			const pane = drawerScroller();
			if (pane) pane.scrollTop = drawerScrollToRestore(drawerScrollMemory, generationInfoTab);
		});
	}
	let generationInfoToggleEl = $state<HTMLButtonElement | null>(null);
	let refineView = $state<'adjust' | 'compare' | 'language'>('adjust');
	let refineModalOpen = $state(false);
	// Refinement dimensions retain the previous selection.
	const REFINE_KIND_KEY = 'inku-refine-kind';
	const REFINE_KINDS: RefineKind[] = ['touch', 'layout', 'reading', 'color', 'variation'];
	let refineKind = $state<RefineKind>('touch');
	let variationAmplitude = $state<VariationAmplitude>('medium');
	onMount(() => {
		try {
			const stored = localStorage.getItem(REFINE_KIND_KEY) as RefineKind | null;
			if (stored && REFINE_KINDS.includes(stored)) refineKind = stored;
		} catch {}
	});
	function setRefineKind(kind: RefineKind) {
		refineKind = kind;
		try { localStorage.setItem(REFINE_KIND_KEY, kind); } catch {}
	}
	// DDL-origin works cannot vary interpretation, so remove a restored choice.
	$effect(() => {
		if (statusDdlOrigin && refineKind === 'reading') refineKind = 'touch';
	});
	const statusGenerationValue = $derived(
		statusGeneration
			? (isJapanese ? `第${statusGeneration}世代` : `Gen. ${statusGeneration}`)
			: (isJapanese ? '独立作品' : 'Standalone')
	);
	async function openLineageRefinement(node: LineageNode, view: 'adjust' | 'compare' | 'language'): Promise<void> {
		await onOpenLineageNode(node);
		refineView = view;
		refineModalOpen = true;
		outputTab = 'refine';
	}

	function closeRefineModal(): void {
		refineModalOpen = false;
		outputTab = 'lineage';
		// Reflect any adopted comparison/variation results into the lineage tree.
		onCloseRefinement();
	}

	const canvasMaxRatio = $derived(Math.max(canvasAspectWidth, canvasAspectHeight, 1));
	const canvasBaseWidth = $derived(400 * canvasAspectWidth / canvasMaxRatio);
	const canvasBaseHeight = $derived(400 * canvasAspectHeight / canvasMaxRatio);
	const displayInstructionText = $derived((instructionText || '').trim());
	const canShowInstructionCaption = $derived(!!displayInstructionText);

	function toggleInstructionCaption() {
		instructionCaptionVisible = !instructionCaptionVisible;
		void onInstructionCaptionVisibleChange(instructionCaptionVisible);
	}

	function updateFitZoom() {
		if (!canvasContentEl) return;
		const rect = canvasContentEl.getBoundingClientRect();
		const availableWidth = Math.max(120, rect.width - 120);
		const availableHeight = Math.max(120, rect.height - 96);
		const nextZoom = Math.max(0.25, Math.min(10, Math.min(availableWidth / canvasBaseWidth, availableHeight / canvasBaseHeight)));
		viewport.updateFitZoom(+nextZoom.toFixed(2));
	}

	onMount(() => {
		updateFitZoom();
		const observer = new ResizeObserver(updateFitZoom);
		if (canvasContentEl) observer.observe(canvasContentEl);
		const wheelTarget = canvasContentEl;
		const onWheel = (event: WheelEvent) => {
			if (outputTab !== 'canvas' || !result) return;
			event.preventDefault();
			const step = event.deltaY < 0 ? 0.15 : -0.15;
			viewport.setZoom(viewport.zoom + step);
		};
		wheelTarget?.addEventListener('wheel', onWheel, { passive: false });
		return () => {
			observer.disconnect();
			wheelTarget?.removeEventListener('wheel', onWheel);
		};
	});

	$effect(() => {
		canvasAspectWidth;
		canvasAspectHeight;
		updateFitZoom();
	});

	function closePresentationMode() {
		presentationMode = false;
	}

	const seedSummary = $derived(
		result
			? t().canvasSeedSummary
				.replace('{render}', result.render_seed == null ? '-' : String(result.render_seed))
				.replace('{composition}', result.composition_seed == null ? t().seedBaseLabel : String(result.composition_seed))
			: ''
	);
	// Since v1.98, identify works drawn with fallback DDL after Stage 1 failed.
	const interpretFallbackReason = $derived(
		statusHistoryItem
			? (statusHistoryItem.interpret_fallback ?? null)
			: (result?.interpret_fallback_used ? (result?.interpret_fallback_reasons?.[0] ?? 'stage1_fallback') : null)
	);
	// Stage 2's counterpart. A saved work reads its column; a work still on the
	// canvas reads the response it was drawn by, which is the only place the
	// fact exists before it is saved.
	const composeFallbackRaw = $derived(
		statusHistoryItem
			? (statusHistoryItem.compose_fallback ?? null)
			: (result ? composeFallbackValue(result) : null)
	);
	const composeFallbackDrawnReason = $derived(composeFallbackReason(composeFallbackRaw));
	// Three readings for the drawer, one condition for the badge. Only Stage 2
	// can tell 'no' from 'unrecorded', so only its row shows three.
	const composeFallbackRecord = $derived(composeFallbackState(composeFallbackRaw));
	// Bytes, objects, and points do not stand in for one another. Measure all
	// three once for both the canvas strip and the generation-information view,
	// using the same definition as the trend report (see $lib/svgWeight).
	// HistoryItem carries no SVG, so this reads the current result directly.
	const detailSvgWeight = $derived(result?.svg ? measureSvgWeight(result.svg) : null);
	const detailSvgBytes = $derived(detailSvgWeight?.bytes ?? null);
</script>

<svelte:window
	onkeydown={(event) => {
		if (event.key !== 'Escape') return;
		if (refineModalOpen) closeRefineModal();
		else if (generationInfoOpen) closeGenerationInfo();
		else if (presentationMode) closePresentationMode();
	}}
	onpointerdown={(event) => {
		// Clicking outside closes the generation drawer; its button toggles itself.
		if (!generationInfoOpen) return;
		const target = event.target as Node | null;
		if (!target) return;
		if (generationInfoEl?.contains(target)) return;
		if (generationInfoToggleEl?.contains(target)) return;
		closeGenerationInfo();
	}}
/>

<div class="right-panel">
	<div class="right-tabs">
		<Tooltip placement="bottom-right" text={t().tooltipCanvasTabCanvas}>
			<button class="rtab" class:active={outputTab === 'canvas'} onclick={() => (outputTab = 'canvas')}>{t().tabCanvas}</button>
		</Tooltip>
		<Tooltip placement="bottom" text={isJapanese ? '作品の派生関係を表示' : 'Show how this work was derived'}>
			<button class="rtab" class:active={outputTab === 'lineage'} onclick={() => (outputTab = 'lineage')} disabled={!result}>{isJapanese ? '系譜' : 'Lineage'}</button>
		</Tooltip>
		<div class="rtab-spacer"></div>
		{#if result}
			<div class="render-meta-strip" aria-label={isJapanese ? '\u8868\u793a\u4e2d\u306e\u4f5c\u54c1\u60c5\u5831' : 'Information about the displayed work'}>
				<span class="render-meta-item render-meta-generation">
					{#if statusGeneration}<span class="render-meta-label">{isJapanese ? '系譜' : 'Lineage'}</span>{/if}
					<strong>{statusGenerationValue}</strong>
				</span>
				<span class="render-meta-item render-meta-model">
					<span class="render-meta-label">{isJapanese ? '\u30e2\u30c7\u30eb' : 'Models'}</span>
					<strong title={statusStage1Model + ' / ' + statusStage2Model}>
						{#if statusStage1Model === statusStage2Model}
							{isJapanese ? '\u89e3\u91c8\uff0f\u63cf\u753b' : 'Interpretation / performance'} {statusStage1ModelOnly}
						{:else}
							{isJapanese ? '\u89e3\u91c8' : 'Interpretation'} {statusStage1ModelOnly} / {isJapanese ? '\u63cf\u753b' : 'Performance'} {statusStage2ModelOnly}
						{/if}
					</strong>
				</span>
				<span class="render-meta-item render-meta-catalog">
					<span class="render-meta-label">{isJapanese ? '\u8272\u30ab\u30bf\u30ed\u30b0' : 'Color catalog'}</span>
					<strong title={statusCatalogName}>{statusCatalogName}</strong>
				</span>
				<span class="render-meta-item render-meta-canvas">
					<span class="render-meta-label">{isJapanese ? '\u30ad\u30e3\u30f3\u30d0\u30b9' : 'Canvas'}</span>
					<strong title={statusCanvasName}>{statusCanvasName}</strong>
				</span>
				<!-- The same byte measurement the drawer shows, rounded to a compact
				     whole-kilobyte capacity in this narrow strip. -->
				<span class="render-meta-item render-meta-svg-size">
					<span class="render-meta-label">{isJapanese ? '\u30b5\u30a4\u30ba' : 'Size'}</span>
					<strong>{formatCanvasCapacity(detailSvgBytes)}</strong>
				</span>
				<span class="render-meta-item render-meta-created">
					<span class="render-meta-label">{isJapanese ? '\u4f5c\u6210' : 'Created'}</span>
					<strong>{currentRenderedAt ?? '-'}</strong>
				</span>
			</div>
		{/if}
	</div>

	<div class="canvas-area">
		<div class="nav-left">
			<Tooltip placement="right" text={t().tooltipCanvasNavLatest}>
				<button class="nav-latest" onclick={onGotoLatest} disabled={interactionLocked || navLatestDisabled}>{t().historyLatest}</button>
			</Tooltip>
			<Tooltip placement="right" text={t().tooltipCanvasNavNewer}>
				<button class="nav-circle" onclick={onGotoNext} disabled={interactionLocked || navNewerDisabled}>‹</button>
			</Tooltip>
		</div>

		{#if outputTab === 'canvas'}
			<CanvasArtworkWorkspace
				{result}
				{artworkUrl}
				bind:canvasContentEl
				{canvasAspectWidth}
				{canvasAspectHeight}
				{canvasBaseWidth}
				{canvasBaseHeight}
				{viewport}
				{unsavedRefinementPreview}
				{interpretFallbackReason}
				{composeFallbackDrawnReason}
				{lineageIntermediateNotice}
				{instructionCaptionVisible}
				{canShowInstructionCaption}
				{displayInstructionText}
				{statusHistoryItem}
				{statusHashLabel}
				{statusHashCopied}
				{replayDisabled}
				{allowEmptyOutputTabs}
				{generationInfoOpen}
				bind:generationInfoToggleEl
				bind:exportMenuOpen
				bind:exportWrapEl
				{exportCardOnly}
				{cardExportBusy}
				bind:svgHelpOpen
				{currentHistoryId}
				{pngTemplates}
				{isJapanese}
				onToggleInstructionCaption={toggleInstructionCaption}
				{onToggleStar}
				{onToggleForRevision}
				{onToggleForShare}
				{onCopyStatusHash}
				{onReplayCurrent}
				onToggleGenerationInfo={() => (generationInfoOpen ? closeGenerationInfo() : openGenerationInfo())}
				{onToggleSaijiki}
				{onDownloadSVG}
				{onDownloadPNG}
				onDownloadCard={downloadCardFromCanvas}
				onOpenPresentation={() => (presentationMode = true)}
			/>
		{:else}
			<!-- svelte-ignore a11y_no_static_element_interactions -->
			<div
				bind:this={canvasContentEl}
				class="canvas-content side-nav-safe"
				class:dragging={viewport.dragging}
				onpointerdown={(event) => viewport.startDrag(event, false)}
				onpointermove={(event) => viewport.moveDrag(event)}
				onpointerup={(event) => viewport.endDrag(event)}
				onpointercancel={(event) => viewport.endDrag(event)}
			>
				{#if outputTab === 'refine'}
				<CanvasRefinementWorkspace
					view={refineView}
					modalOpen={refineModalOpen}
					{isJapanese}
					resultAvailable={!!result}
					{artworkUrl}
					{seedSummary}
					{canvasAspectWidth}
					{canvasAspectHeight}
					{refinementSession}
					{modelInspection}
					{activeComparisonItem}
					{statusDdlOrigin}
					{refineKind}
					bind:variationAmplitude
					bind:touchSeedText
					{statusStage1Model}
					{statusStage2Model}
					{refineDrawingModelId}
					{refineDrawingModelGroups}
					{refineWildValue}
					{refineWildInherited}
					onClose={closeRefineModal}
					onSetRefineKind={setRefineKind}
					{onGenerateVariationCandidates}
					{onSaveSelectedVariationCandidates}
					{onShowVariationCandidate}
					{onSelectRefineDrawingModel}
					{onSetRefineWild}
				/>
			{:else if outputTab === 'lineage'}
				{#await import('./LineagePanel.svelte') then { default: LineagePanel }}
					<LineagePanel graph={lineageGraph} loading={lineageLoading} error={lineageError} {isJapanese} {nearbyHistory} {onOpenNearbyHistory} onOpenNode={onOpenLineageNode} onOpenNodeInCanvas={onOpenLineageNodeInCanvas} onToggleStar={onToggleLineageStar} onToggleForRevision={onToggleLineageForRevision} onOpenRefinement={openLineageRefinement} onDrawDescription={onDrawLineageDescription} onDrawDdl={onDrawLineageDdl} onOpenDdlEditor={onOpenLineageDdlEditor} onDrawSketchGrain={onDrawLineageSketchGrain} {stageLabel} stage1ModelLabel={statusStage1Model} stage2ModelLabel={statusStage2Model} {runTokensIn} {runTokensOut} onSaveOkugakiModel={onSaveOkugakiModel} {onSaveVisionModel} onPromoteNode={onPromoteLineageNode} onSaveNote={onSaveLineageNote} onAskTrash={onAskTrashLineage} onDetach={onDetachLineage} onLoadOverview={onLoadLineageOverview} onLoadBranch={onLoadLineageBranch} {onPaintOne} {onVisionAdvice} {visionModel} {okugakiModel} {visionProviderGroups} {animationExportSettings} {apiFetch} {catalogName} {formatHistoryDate} {historyPreviewText} />
				{/await}
			{/if}
		</div>
		{/if}



		<div class="nav-right">
			<Tooltip placement="left" text={t().tooltipCanvasNavOlder}>
				<button class="nav-circle" onclick={onGotoPrev} disabled={interactionLocked || navOlderDisabled}>›</button>
			</Tooltip>
			{#if historyTotal > 0}
				<span class="nav-counter">{navPos} / {historyTotal}</span>
			{/if}
		</div>
	</div>

	<CanvasGenerationInfo
		open={generationInfoOpen}
		bind:tab={generationInfoTab}
		bind:drawerEl={generationInfoEl}
		bind:detailsScrollEl
		bind:tabsScrollEl
		{result}
		{statusHistoryItem}
		{isJapanese}
		{developerMode}
		{statusTenkei}
		{statusGeneration}
		{statusStage1Model}
		{statusStage2Model}
		{statusCatalogName}
		{statusCanvasName}
		{currentRenderedAt}
		{interpretFallbackReason}
		{composeFallbackRecord}
		{composeFallbackDrawnReason}
		detailSvgWeight={detailSvgWeight}
		detailSvgBytes={detailSvgBytes}
		{statusHashLabel}
		{statusHashCopied}
		{promptsData}
		{stage1PromptText}
		{ddl}
		bind:promptStage1Expanded
		bind:promptStage2Expanded
		{copiedPrompt}
		{scoreJsonText}
		{scoreJsonLines}
		{scoreJsonHighlighted}
		{scoreJsonSeparatorLine}
		onClose={closeGenerationInfo}
		{onCopyStatusHash}
		{onCopyPromptText}
	/>


</div>

{#if presentationMode && result}
	<CanvasPresentationOverlay
		{artworkUrl}
		{instructionCaptionVisible}
		{canShowInstructionCaption}
		{displayInstructionText}
		{interactionLocked}
		{navNewerDisabled}
		{navLatestDisabled}
		{navOlderDisabled}
		{historyTotal}
		{navPos}
		workMark={statusHistoryItem}
		{onGotoNext}
		{onGotoLatest}
		{onGotoPrev}
		onToggleStar={(event) => onToggleStar(statusHistoryItem, event)}
		onToggleCaption={toggleInstructionCaption}
		onClose={closePresentationMode}
	/>
{/if}

<style>
	.right-panel {
		position: relative;
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.right-tabs {
		display: flex;
		align-items: center;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		padding: 0 16px;
		flex-shrink: 0;
	}
	.rtab {
		padding: 9px 16px;
		border: none;
		border-bottom: 2px solid transparent;
		background: none;
		color: var(--fg2);
		font-size: 13px;
		cursor: pointer;
		font-family: inherit;
		white-space: nowrap;
	}
	.rtab.active { border-bottom-color: var(--fg); color: var(--fg); font-weight: 500; }
	.rtab:hover:not(.active):not(:disabled) { color: var(--fg); }
	.rtab:disabled { opacity: 0.35; cursor: not-allowed; }
	.rtab-spacer { flex: 0 0 12px; }
	.render-meta-strip {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 10px;
		min-width: 0;
		flex: 1 1 auto;
		max-width: none;
		overflow: hidden;
		font-size: 11px;
		color: var(--fg3);
	}
	.render-meta-generation { flex: 0 0 auto; }
	.render-meta-generation strong { max-width: none; }
	.render-meta-item {
		display: inline-flex;
		align-items: baseline;
		gap: 4px;
		min-width: 0;
		white-space: nowrap;
	}
	.render-meta-label { color: var(--fg3); }
	.render-meta-item strong {
		min-width: 0;
		max-width: 160px;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--fg2);
		font-weight: 400;
	}
	.render-meta-model strong { max-width: 220px; }
	.render-meta-catalog strong { max-width: 130px; }
	.render-meta-canvas strong { max-width: 100px; }
	/* The two numeric items: never ellipsised, and set on the digit grid so a
	   size and a timestamp do not jitter as the work on screen changes. */
	.render-meta-created strong,
	.render-meta-svg-size strong {
		max-width: none;
		font-variant-numeric: tabular-nums;
	}
	@media (max-width: 1180px) {
		.right-tabs { flex-wrap: wrap; padding-inline: 10px; }
		.rtab { padding-inline: 12px; }
		.rtab-spacer { display: none; }
		.render-meta-strip {
			order: 2;
			flex: 1 0 100%;
			justify-content: flex-start;
			gap: 12px;
			padding: 4px 0 6px;
			flex-wrap: wrap;
			overflow: visible;
		}
		.render-meta-item { flex: 0 1 auto; }
		.render-meta-item strong { max-width: 180px; }
	}
	.canvas-area {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg2);
		position: relative;
		overflow: hidden;
	}
	.nav-left,
	.nav-right {
		position: absolute;
		z-index: 10;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
	}
	.nav-left { left: 14px; }
	.nav-right { right: 14px; }

	.nav-circle {
		width: 38px;
		height: 38px;
		border-radius: 50%;
		background: var(--floating-control-bg);
		border: 1px solid var(--border2);
		font-size: 20px;
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--floating-control-fg);
		cursor: pointer;
		font-family: inherit;
		transition: background 0.1s;
	}
	.nav-circle:hover:not(:disabled) { background: var(--floating-control-hover); }
	.nav-latest {
		min-width: 42px;
		height: 24px;
		border-radius: 999px;
		background: var(--floating-control-bg);
		border: 1px solid var(--border2);
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		color: var(--floating-control-fg);
		cursor: pointer;
		font-size: 11px;
		font-family: inherit;
		line-height: 1;
		padding: 0 8px;
	}
	.nav-latest:hover:not(:disabled) { background: var(--floating-control-hover); }
	.nav-circle:disabled {
		background: var(--floating-control-disabled-bg);
		color: var(--floating-control-muted);
		opacity: 1;
		cursor: not-allowed;
	}
	.nav-latest:disabled {
		background: var(--floating-control-disabled-bg);
		color: var(--floating-control-muted);
		opacity: 1;
		cursor: not-allowed;
	}
	.nav-counter { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; white-space: nowrap; }
	.canvas-content {
		position: relative;
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}
	.canvas-content.side-nav-safe {
		box-sizing: border-box;
		padding-left: 68px;
		padding-right: 68px;
	}
</style>
