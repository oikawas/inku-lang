<script lang="ts">
	import { onMount, tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { placeholderMotifTransform } from '$lib/canvas-placeholder';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import type { Score } from '$lib/historyManagerState.svelte';
	import type { Provider, ProviderGroup } from '$lib/models';
	import CanvasGenerationInfo from '$lib/features/canvas/CanvasGenerationInfo.svelte';
	import CanvasPresentationOverlay from '$lib/features/canvas/CanvasPresentationOverlay.svelte';
	import CanvasRefinementWorkspace from '$lib/features/canvas/CanvasRefinementWorkspace.svelte';
	import type { LineageGraph, LineageNode, NearbyWork } from '$lib/features/history/types';
	import { measureSvgWeight } from '$lib/svgWeight';
	import { formatByteSize } from '$lib/formatNumber';
	import { shareTargetOf } from '$lib/shareTarget';
	import { drawerScrollToRestore, emptyDrawerScrollMemory, rememberDrawerScroll, type DrawerTab } from '$lib/drawerScroll';
	import type { DerivationKind } from '$lib/derivation';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';

	type ModelInspection = ReturnType<typeof createModelInspection>;
	import Tooltip from './Tooltip.svelte';
	import { composeFallbackReason, composeFallbackState, composeFallbackValue } from '$lib/composeFallback';
	import type { ColorMap } from '$lib/colors';
	import type { CanvasViewport } from '$lib/features/canvas/viewport-state.svelte';
	import type {
		RefinementSession,
		RefineKind,
		VariationAmplitude,
		VariationCandidate
	} from '$lib/features/canvas/refinement-session.svelte';

	type OutputTab = 'canvas' | 'refine' | 'lineage';
	type SvgProfile = 'display' | 'editable' | 'compat';
	type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
	type PaintResult = { svg: string; score: Score; interpret_fallback_used?: boolean; interpret_fallback_reasons?: string[]; compose_fallback_used?: boolean; compose_retry_reasons?: string[]; description_hash?: string | null; render_build_number?: string | null; render_engine_id?: string | null; render_engine_version?: string | null; ddl_version?: string | null; ddl_engine_version?: string | null; render_hash?: string | null; render_hash_short?: string | null; render_seed?: number | null; render_wild?: boolean | null; seed_text?: string | null; focus?: string | null; composition_seed?: number | null; interpretation_seed?: string | null; variation_amplitude?: string | null; variation_seed?: number | null; variation_moved_axes?: Array<{ axis: string; from: string; to: string }>; stage1_prompt_digest?: string | null; stage1_prompt_base_digest?: string | null; stage2_prompt_digest?: string | null; render_color_map?: ColorMap | null; render_canvas_aspect_ratio?: number | null; derivation_kind?: DerivationKind | null; instruction_lang_requested?: string | null; instruction_lang_resolved?: string | null; ui_lang?: string | null; sketch_grain?: string | null; sketch_state?: string | null; derivation_metadata?: Record<string, unknown>; elapsed_stage1_ms: number; elapsed_stage2_ms: number; elapsed_total_ms: number; tokens_in_stage1: number | null; tokens_out_stage1: number | null; tokens_in_stage2: number | null; tokens_out_stage2: number | null };
	type PromptsData = { stage1_system: string; stage2_system: string };
	type HistoryItem = { id?: string; starred?: boolean; for_revision?: boolean; for_share?: boolean; note?: string | null; interpret_fallback?: string | null; compose_fallback?: string | null; description_hash?: string | null; render_build_number?: string | null; render_engine_id?: string | null; render_engine_version?: string | null; ddl_version?: string | null; ddl_engine_version?: string | null; render_hash?: string | null; render_seed?: number | string | null; render_wild?: boolean | null; seed_text?: string | null; focus?: string | null; composition_seed?: number | string | null; interpretation_seed?: string | null; variation_amplitude?: string | null; variation_seed?: number | string | null; stage1_prompt_digest?: string | null; stage1_prompt_base_digest?: string | null; stage2_prompt_digest?: string | null; render_color_map?: ColorMap | null; render_canvas_aspect_ratio?: number | null; derivation_kind?: string | null; batch_run_id?: string | null; batch_line_number?: number | null; instruction_lang_requested?: string | null; instruction_lang_resolved?: string | null; ui_lang?: string | null; sketch_grain?: string | null; sketch_state?: string | null; derivation_metadata?: Record<string, unknown>; elapsed_ms?: number; tokens_in?: number | null; tokens_out?: number | null };
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

	let canvasContentEl: HTMLDivElement | null = null;

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
	const placeholderUnit = $derived(Math.max(0.001, Math.min(canvasAspectWidth, canvasAspectHeight)));
	const placeholderWidth = $derived(Math.round(1000 * canvasAspectWidth / placeholderUnit));
	const placeholderHeight = $derived(Math.round(1000 * canvasAspectHeight / placeholderUnit));
	// The motif is drawn in a square of its own and centred in the frame, so a
	// circle stays a circle and a square stays a square whatever the canvas
	// proportion is. Writing each coordinate as a fraction of the width AND of
	// the height -- which is what this did -- makes the shapes take the frame's
	// proportion: at Pillar (1:5) the triangle became a needle. The placement
	// itself lives in $lib/canvas-placeholder so it can be measured.
	const placeholderTransform = $derived(placeholderMotifTransform(placeholderWidth, placeholderHeight));
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

	function isDefaultPngTemplate(template: ExportTemplate): boolean {
		return template.id === `png-${template.y_px}` && [1080, 2160, 4320].includes(template.y_px);
	}

	function pngTemplateDescription(template: ExportTemplate): string {
		if (isDefaultPngTemplate(template)) return t().pngYAxisDescription(template.y_px);
		return template.description || t().pngYAxisDescription(template.y_px);
	}

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
	// The third mark's socket. `supported` is false everywhere today, so the
	// button below renders nothing -- see $lib/shareTarget and ledger I-191.
	const shareTarget = $derived(shareTargetOf(statusHistoryItem));
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
				<span class="render-meta-scope">{isJapanese ? '\u8868\u793a\u4e2d' : 'Displayed'}</span>
				<span class="render-meta-item render-meta-generation">
					{#if statusGeneration}<span class="render-meta-label">{isJapanese ? '系譜' : 'Lineage'}</span>{/if}
					<strong>{statusGenerationValue}</strong>
				</span>
				<span class="render-meta-item render-meta-model">
					<span class="render-meta-label">{isJapanese ? '\u30e2\u30c7\u30eb' : 'Models'}</span>
					<strong title={statusStage1Model + ' / ' + statusStage2Model}>
						{#if statusStage1Model === statusStage2Model}
							{isJapanese ? '\u89e3\u91c8\uff0f\u63cf\u753b' : 'Interpretation / performance'} {statusStage1Model}
						{:else}
							{isJapanese ? '\u89e3\u91c8' : 'Interpretation'} {statusStage1Model} / {isJapanese ? '\u63cf\u753b' : 'Performance'} {statusStage2Model}
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
				<!-- The same measurement the drawer shows, formatted by the same
				     function: one quantity, said in two places. -->
				<span class="render-meta-item render-meta-svg-size">
					<span class="render-meta-label">{isJapanese ? 'SVG \u30b5\u30a4\u30ba' : 'SVG size'}</span>
					<strong>{formatByteSize(detailSvgBytes)}</strong>
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

		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			bind:this={canvasContentEl}
			class="canvas-content"
			class:can-pan={outputTab === 'canvas' && viewport.canPan}
			class:dragging={viewport.dragging}
			class:side-nav-safe={outputTab !== 'canvas'}
			onpointerdown={(event) => viewport.startDrag(event, outputTab === 'canvas')}
			onpointermove={(event) => viewport.moveDrag(event)}
			onpointerup={(event) => viewport.endDrag(event)}
			onpointercancel={(event) => viewport.endDrag(event)}
		>
			{#if outputTab === 'canvas'}
				<div class="canvas-pan" style="transform: translate3d({viewport.panX}px, {viewport.panY}px, 0);">
					<div
						class="canvas-box"
						style="width: {canvasBaseWidth}px; height: {canvasBaseHeight}px; transform: scale({viewport.actualZoom}); transform-origin: center center; transition: transform 0.15s;"
					>
						{#if result}
							{#if artworkUrl}
								<img class="canvas-art" src={artworkUrl} alt="" />
							{/if}
						{:else}
							<div class="canvas-placeholder-art" aria-label={t().canvasPlaceholder}>
								<svg viewBox="0 0 {placeholderWidth} {placeholderHeight}" role="img">
									<rect x="0" y="0" width={placeholderWidth} height={placeholderHeight} rx="6" fill="#fffdf8" />
									<!-- Mountain, water, moon: three strokes, authored inside the
									     1000-square PLACEHOLDER_MOTIF frame and placed by one uniform
									     scale, so the moon stays round and the ridge keeps its angles
									     at every canvas proportion. No coordinate here is written as a
									     fraction of the frame -- that is what turned the old triangle
									     into a needle at Pillar (1:5). -->
									<g opacity="0.72" transform={placeholderTransform}>
										<path d="M 110 645 L 320 360 L 505 545 L 640 445 L 890 645" fill="none" stroke="#cfc6b6" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
										<path d="M 110 748 C 215 700 300 800 400 748 C 500 696 585 796 685 748 C 780 700 838 782 890 754" fill="none" stroke="#ded6c9" stroke-width="4" stroke-linecap="round" />
										<circle cx="690" cy="260" r="80" fill="none" stroke="#d8cfc0" stroke-width="6" />
									</g>
								</svg>
							</div>
						{/if}
					</div>
				</div>
{#if unsavedRefinementPreview}
	<div class="unsaved-refinement-badge" role="status">{t().unsavedRefinementPreviewLabel}</div>
{/if}
{#if interpretFallbackReason || composeFallbackDrawnReason}
	<!-- Stacked, and one badge per layer: a work whose interpretation and whose
	     composition both fell has lost the words twice, and a single badge would
	     say it once. The wording names the layer for the same reason. -->
	<div class="fallback-badges" role="status">
		{#if interpretFallbackReason}
			<div class="interpret-fallback-badge" title={t().interpretFallbackHint(interpretFallbackReason)}>{t().interpretFallbackBadge}</div>
		{/if}
		{#if composeFallbackDrawnReason}
			<div class="compose-fallback-badge" title={t().composeFallbackHint(composeFallbackDrawnReason)}>{t().composeFallbackBadge}</div>
		{/if}
	</div>
{/if}
{#if lineageIntermediateNotice}
	<div class="lineage-intermediate-notice" role="status">{lineageIntermediateNotice}</div>
{/if}
				<!-- The marks a reader puts on the work in front of them: it is a
				     favourite, it wants another pass. They sit beside the caption
				     toggle rather than in a bar of their own, because all three are
				     about the drawing on screen and nothing else. -->
				<div class="canvas-corner-controls canvas-corner-left" onpointerdown={(event) => event.stopPropagation()}>
					<Tooltip placement="top-right" text={t().tooltipCanvasCaption}>
						<button
							type="button"
							class="canvas-icon-btn canvas-caption-btn"
							class:active={instructionCaptionVisible}
							disabled={!canShowInstructionCaption}
							aria-label={t().canvasCaptionToggle}
							onclick={(event) => {
								event.stopPropagation();
								toggleInstructionCaption();
							}}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<rect x="3.5" y="5.5" width="17" height="13" rx="2.5" />
								<path d="M7.5 10.5h4.5M14.5 10.5h2M7.5 14h3M13 14h3.5" />
							</svg>
						</button>
					</Tooltip>
					<Tooltip placement="top-right" text={statusHistoryItem?.starred ? t().starOn : t().starOff}>
						<button
							type="button"
							class="canvas-icon-btn canvas-star-btn"
							class:marked={!!statusHistoryItem?.starred}
							disabled={!statusHistoryItem?.id}
							aria-pressed={!!statusHistoryItem?.starred}
							aria-label={statusHistoryItem?.starred ? t().starOn : t().starOff}
							onclick={(event) => {
								event.stopPropagation();
								onToggleStar(statusHistoryItem, event);
							}}
						>★</button>
					</Tooltip>
					<Tooltip placement="top-right" text={statusHistoryItem?.for_revision ? t().forRevisionOn : t().forRevisionOff}>
						<button
							type="button"
							class="canvas-icon-btn canvas-revision-btn"
							class:marked={!!statusHistoryItem?.for_revision}
							disabled={!statusHistoryItem?.id}
							aria-pressed={!!statusHistoryItem?.for_revision}
							aria-label={statusHistoryItem?.for_revision ? t().forRevisionOn : t().forRevisionOff}
							onclick={(event) => {
								event.stopPropagation();
								onToggleForRevision(statusHistoryItem, event);
							}}
						>✎</button>
					</Tooltip>
					{#if shareTarget.supported && onToggleForShare}
						<Tooltip placement="top-right" text={shareTarget.marked ? t().shareTargetOn : t().shareTargetOff}>
							<button
								type="button"
								class="canvas-icon-btn canvas-share-btn"
								class:marked={shareTarget.marked}
								disabled={!shareTarget.pressable}
								aria-pressed={shareTarget.marked}
								aria-label={shareTarget.marked ? t().shareTargetOn : t().shareTargetOff}
								onclick={(event) => {
									event.stopPropagation();
									onToggleForShare?.(statusHistoryItem, event);
								}}
							>
								<svg viewBox="0 0 24 24" aria-hidden="true">
									<circle cx="17.5" cy="6" r="2.6" />
									<circle cx="6.5" cy="12" r="2.6" />
									<circle cx="17.5" cy="18" r="2.6" />
									<path d="M9 10.7 15 7.3M9 13.3l6 3.4" />
								</svg>
							</button>
						</Tooltip>
					{/if}
				</div>
				<!-- What the bar under the canvas used to hold. It is here rather
				     than below the picture because every one of these acts on the
				     work being looked at; the fullscreen button stays last, at the
				     corner, so it keeps the position it has always had. -->
				<div class="canvas-corner-controls canvas-corner-right" onpointerdown={(event) => event.stopPropagation()}>
					{#if statusHashLabel}
						<Tooltip placement="top-left" text={statusHashCopied ? (isJapanese ? 'コピーしました' : 'Copied') : (isJapanese ? 'クリックでfull hashをコピーします' : 'Click to copy the full hash')}>
							<button
								type="button"
								class="canvas-icon-btn canvas-hash-btn"
								class:marked={statusHashCopied}
								aria-label={isJapanese ? 'full hash をコピー' : 'Copy the full hash'}
								onclick={onCopyStatusHash}
							>#</button>
						</Tooltip>
					{/if}
					<Tooltip placement="top-left" text={t().historyReplayTitle}>
						<button
							type="button"
							class="canvas-icon-btn canvas-replay-btn"
							disabled={replayDisabled}
							aria-label={t().historyReplay}
							onclick={onReplayCurrent}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M20 12a8 8 0 1 1-2.6-5.9" />
								<path d="M20 4v4h-4" />
							</svg>
						</button>
					</Tooltip>
					<Tooltip placement="top-left" text={isJapanese ? '選択中作品の生成情報を表示' : 'Show the provenance, prompts, and JSON of the chosen work'}>
						<button
							bind:this={generationInfoToggleEl}
							type="button"
							class="canvas-icon-btn canvas-provenance-btn"
							class:active={generationInfoOpen}
							disabled={!result && !allowEmptyOutputTabs}
							aria-expanded={generationInfoOpen}
							aria-label={isJapanese ? '生成情報' : 'Provenance'}
							onclick={() => (generationInfoOpen ? closeGenerationInfo() : openGenerationInfo())}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<circle cx="12" cy="12" r="8.5" />
								<path d="M12 11v5.5M12 7.8v.4" />
							</svg>
						</button>
					</Tooltip>
					<Tooltip placement="top-left" text={t().tooltipSaijikiToggle}>
						<button
							type="button"
							class="canvas-icon-btn canvas-saijiki-btn"
							data-saijiki-toggle
							aria-label={t().saijikiToggleBtn}
							onclick={onToggleSaijiki}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M5 5.5h5.5a1.5 1.5 0 0 1 1.5 1.5v11a1.2 1.2 0 0 0-1.2-1.2H5z" />
								<path d="M19 5.5h-5.5a1.5 1.5 0 0 0-1.5 1.5v11a1.2 1.2 0 0 1 1.2-1.2H19z" />
							</svg>
						</button>
					</Tooltip>
					<!-- One door for the three ways a work leaves: SVG, PNG, and the
					     share card. They were three buttons side by side, which said
					     three things where the reader wanted one. -->
					<div class="canvas-export" bind:this={exportWrapEl}>
						<Tooltip placement="top-left" text={exportCardOnly ? t().historyCardExport : t().exportLabel}>
							<button
								type="button"
								class="canvas-icon-btn canvas-export-btn"
								class:active={exportMenuOpen && !exportCardOnly}
								disabled={exportCardOnly ? (!currentHistoryId || cardExportBusy) : !result}
								aria-haspopup={exportCardOnly ? undefined : 'menu'}
								aria-expanded={exportCardOnly ? undefined : exportMenuOpen}
								aria-label={exportCardOnly ? t().historyCardExport : t().exportLabel}
								onclick={(e) => {
									e.stopPropagation();
									// One button, two jobs, decided by which tools the reader kept.
									// With the work tools gone there is nothing to choose between,
									// so opening a menu of one would be a door onto a door.
									if (exportCardOnly) downloadCardFromCanvas();
									else exportMenuOpen = !exportMenuOpen;
								}}
							>
								<svg class="download-icon" viewBox="0 0 24 24" aria-hidden="true">
									<path d="M12 3v11m0 0 4-4m-4 4-4-4M5 18h14" />
								</svg>
							</button>
						</Tooltip>
						{#if exportMenuOpen && !exportCardOnly}
							<div class="export-menu" role="menu">
								<div class="export-menu-group">
									<div class="svg-menu-head">
										<span>{t().svgExportHelpTitle}</span>
										<button
											type="button"
											class="svg-help-btn"
											aria-label={t().svgExportHelpAria}
											onclick={(e) => { e.stopPropagation(); svgHelpOpen = !svgHelpOpen; }}
										>?</button>
									</div>
									{#if svgHelpOpen}
										<div class="svg-help-popover">
											<table>
												<thead>
													<tr><th>{t().svgExportTableFormat}</th><th>{t().svgExportTableUse}</th><th>{t().svgExportTableFeature}</th></tr>
												</thead>
												<tbody>
													<tr><td>{t().svgExportDisplayName}</td><td>{t().svgExportDisplayUse}</td><td>{t().svgExportDisplayFeature}</td></tr>
													<tr><td>{t().svgExportEditableName}</td><td>{t().svgExportEditableUse}</td><td>{t().svgExportEditableFeature}</td></tr>
													<tr><td>{t().svgExportCompatName}</td><td>{t().svgExportCompatUse}</td><td>{t().svgExportCompatFeature}</td></tr>
												</tbody>
											</table>
										</div>
									{/if}
									<button onclick={() => { onDownloadSVG('display'); exportMenuOpen = false; }}>
										<span class="png-size">{t().svgExportDisplayName}</span>
										<span class="png-sub">{t().svgExportDisplaySub}</span>
									</button>
									<button onclick={() => { onDownloadSVG('editable'); exportMenuOpen = false; }}>
										<span class="png-size">{t().svgExportEditableName}</span>
										<span class="png-sub">{t().svgExportEditableSub}</span>
									</button>
									<button onclick={() => { onDownloadSVG('compat'); exportMenuOpen = false; }}>
										<span class="png-size">{t().svgExportCompatName}</span>
										<span class="png-sub">{t().svgExportCompatSub}</span>
									</button>
								</div>
								<div class="export-menu-group">
									<div class="export-menu-head">PNG</div>
									{#each pngTemplates as template (template.id)}
										<button onclick={() => { onDownloadPNG(template.y_px); exportMenuOpen = false; }}>
											<span class="png-size">{template.name}</span>
											<span class="png-sub">{pngTemplateDescription(template)}</span>
										</button>
									{/each}
								</div>
								<div class="export-menu-group">
									<button
										type="button"
										disabled={!currentHistoryId || cardExportBusy}
										onclick={() => { downloadCardFromCanvas(); exportMenuOpen = false; }}
									>
										<span class="png-size">{cardExportBusy ? t().cardExportBusy : t().historyCardExport}</span>
										<span class="png-sub">{t().tooltipCanvasDownloadCard}</span>
									</button>
								</div>
							</div>
						{/if}
					</div>
					<Tooltip placement="top-left" text={t().tooltipCanvasPresentation}>
						<button
							type="button"
							class="canvas-icon-btn canvas-presentation-btn"
							disabled={!result}
							aria-label={t().canvasPresentationOpen}
							onclick={(event) => {
								event.stopPropagation();
								presentationMode = true;
							}}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M8.5 4.5h-4v4M15.5 4.5h4v4M8.5 19.5h-4v-4M15.5 19.5h4v-4" />
								<path d="M8 8 4.5 4.5M16 8l3.5-3.5M8 16l-3.5 3.5M16 16l3.5 3.5" />
							</svg>
						</button>
					</Tooltip>
				</div>
				{#if instructionCaptionVisible && canShowInstructionCaption}
					<div class="instruction-caption" aria-live="polite">{displayInstructionText}</div>
				{/if}
			{:else if outputTab === 'refine'}
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

		{#if outputTab === 'canvas'}
			<div class="zoom-controls">
				<Tooltip text={t().tooltipCanvasZoomOut}>
					<button onclick={() => viewport.setZoom(viewport.zoom - 0.25)}>−</button>
				</Tooltip>
				<span class="zoom-pct">{Math.round(viewport.zoom * 100)}%</span>
				<Tooltip text={t().tooltipCanvasZoomIn}>
					<button onclick={() => viewport.setZoom(viewport.zoom + 0.25)}>＋</button>
				</Tooltip>
				<Tooltip text={t().tooltipCanvasZoomReset}>
					<button class="zoom-reset" onclick={() => viewport.fit()}>⊙</button>
				</Tooltip>
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
	.render-meta-scope { flex: 0 0 auto; border-radius: 999px; padding: 3px 7px; background: var(--bg2); color: var(--fg2); font-size: 10px; font-weight: 600; white-space: nowrap; }
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
	.unsaved-refinement-badge { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 5; padding: 5px 9px; border: 1px solid var(--border2); border-radius: 999px; background: color-mix(in srgb, var(--panel) 94%, transparent); color: var(--fg2); box-shadow: 0 2px 10px #0002; font-size: 11px; white-space: nowrap; }
	/* The stack owns the corner; each badge only paints itself, so a second one
	   sits under the first instead of on top of it. */
	.fallback-badges { position: absolute; top: 12px; right: 12px; z-index: 5; display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
	.interpret-fallback-badge, .compose-fallback-badge { padding: 5px 9px; border: 1px solid #c08a3e; border-radius: 999px; background: color-mix(in srgb, #f6e2bd 88%, transparent); color: #6b4410; box-shadow: 0 2px 10px #0002; font-size: 11px; white-space: nowrap; }
	:global(html[data-theme='dark']) .interpret-fallback-badge, :global(html[data-theme='dark']) .compose-fallback-badge { border-color: #d8a75c; background: color-mix(in srgb, #5a4318 88%, transparent); color: #f4dcb0; }
	.lineage-intermediate-notice { position: absolute; top: 48px; left: 50%; transform: translateX(-50%); z-index: 6; max-width: min(520px, calc(100% - 48px)); padding: 7px 10px; border-radius: var(--r); background: var(--tooltip-bg); color: var(--tooltip-fg); box-shadow: 0 4px 18px #0004; font-size: 11px; line-height: 1.45; text-align: center; }
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
	.canvas-content.can-pan { cursor: grab; touch-action: none; }
	.canvas-content.dragging { cursor: grabbing; }
	.canvas-pan {
		display: flex;
		align-items: center;
		justify-content: center;
		will-change: transform;
	}
	.canvas-box {
		width: 400px;
		height: 400px;
		background: var(--panel);
		box-shadow: 0 8px 32px rgba(0,0,0,0.18);
		overflow: hidden;
		flex-shrink: 0;
	}
	.canvas-box :global(> svg) { width: 100%; height: 100%; display: block; }
	/* The drawing arrives as an image now; it fills the box the same way the
	   inline SVG did, so zoom and pan keep working off the boxes around it. */
	.canvas-box > .canvas-art { width: 100%; height: 100%; display: block; }
	.canvas-placeholder-art {
		width: 100%;
		height: 100%;
		min-height: 200px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--fg3);
		font-size: 13px;
		background: var(--canvas-paper);
	}
	.canvas-placeholder-art svg {
		width: 100%;
		height: 100%;
		display: block;
	}
	.canvas-corner-controls {
		position: absolute;
		bottom: 14px;
		z-index: 11;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.canvas-corner-left { left: 18px; }
	.canvas-corner-right { right: 18px; }
	.canvas-icon-btn {
		width: 34px;
		height: 34px;
		border: 1px solid var(--border2);
		border-radius: 999px;
		background: var(--floating-control-bg);
		color: var(--floating-control-fg);
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
	}
	.canvas-icon-btn:hover:not(:disabled),
	.canvas-icon-btn.active {
		background: var(--floating-control-hover);
		border-color: rgba(77,95,134,0.45);
	}
	.canvas-icon-btn:disabled {
		background: var(--floating-control-disabled-bg);
		color: var(--floating-control-muted);
		cursor: not-allowed;
	}
	.canvas-icon-btn svg {
		width: 18px;
		height: 18px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.9;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	/* Three of these are glyphs rather than drawn paths: the star and the
	   pencil are the marks the history manager already uses for the same two
	   flags, and the hash is the character the value itself starts with. */
	.canvas-star-btn, .canvas-revision-btn, .canvas-hash-btn {
		font-family: inherit;
		font-size: 15px;
		line-height: 1;
	}
	.canvas-hash-btn { font-weight: 600; }
	/* `marked` is a flag standing on the work, not a pressed button: it has to
	   read as on while the pointer is somewhere else entirely. */
	.canvas-star-btn.marked {
		color: var(--star-fg);
		border-color: var(--star-border);
		background: var(--star-bg);
	}
	.canvas-revision-btn.marked,
	.canvas-hash-btn.marked {
		color: var(--accent);
		border-color: var(--accent);
		background: var(--accent-light);
	}
	.canvas-export-btn .download-icon { width: 18px; height: 18px; }
	.instruction-caption {
		position: absolute;
		left: 10%;
		right: 10%;
		bottom: 58px;
		z-index: 12;
		box-sizing: border-box;
		padding: 9px 14px;
		border-radius: 8px;
		background: rgba(17,17,17,0.78);
		color: #fffdf8;
		font-size: 14px;
		line-height: 1.55;
		text-align: center;
		box-shadow: 0 4px 18px rgba(0,0,0,0.22);
		max-height: 5.1em;
		overflow: hidden;
	}
	.zoom-controls {
		position: absolute;
		bottom: 14px;
		left: 50%;
		transform: translateX(-50%);
		z-index: 10;
		display: flex;
		align-items: center;
		gap: 0;
		background: var(--floating-control-bg);
		border: 1px solid var(--border2);
		border-radius: 20px;
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		overflow: hidden;
	}
	.zoom-controls button {
		width: 32px;
		height: 28px;
		border: none;
		background: none;
		font-size: 16px;
		color: var(--floating-control-fg);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: inherit;
	}
	.zoom-controls button:hover { background: var(--floating-control-hover); }
	.zoom-pct {
		font-size: 11px;
		color: var(--floating-control-fg);
		font-weight: 500;
		font-variant-numeric: tabular-nums;
		min-width: 38px;
		text-align: center;
		user-select: none;
	}
	.zoom-reset { border-left: 1px solid var(--border) !important; font-size: 11px !important; color: var(--floating-control-muted) !important; }
	.download-icon {
		width: 14px;
		height: 14px;
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
		stroke-linejoin: round;
		flex: 0 0 auto;
		display: block;
		transform: translateY(0.5px);
	}
	/* The export menu hangs off the corner controls, so it opens upward from a
	   button that sits at the bottom of the canvas. */
	.canvas-export { position: relative; display: inline-flex; }
	.export-menu {
		position: absolute;
		bottom: calc(100% + 6px);
		right: 0;
		z-index: 100;
		background: var(--panel);
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		overflow: hidden;
		box-shadow: 0 4px 18px rgba(0,0,0,0.12);
		min-width: 220px;
	}
	.export-menu > .export-menu-group > button {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		text-align: left;
		padding: 8px 14px;
		background: none;
		border: none;
		border-bottom: 1px solid var(--border);
		color: var(--fg);
		cursor: pointer;
		font-family: inherit;
		font-size: 13px;
		white-space: nowrap;
	}
	.export-menu-group:last-child > button:last-child { border-bottom: none; }
	.export-menu > .export-menu-group > button:hover:not(:disabled) { background: var(--bg); }
	.export-menu > .export-menu-group > button:disabled { opacity: .45; cursor: not-allowed; }
	/* The three ways out are one list, divided rather than stacked in three
	   boxes: a rule says "another kind" without spending the height a second
	   frame would. */
	.export-menu-group + .export-menu-group { border-top: 2px solid var(--border2); }
	.export-menu-head {
		padding: 7px 14px 3px;
		color: var(--fg3);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: .08em;
	}
	.png-size { font-weight: 500; }
	.png-sub { color: var(--fg3); font-size: 11px; white-space: nowrap; }
	.svg-menu-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 8px 12px;
		border-bottom: 1px solid var(--border);
		color: var(--fg2);
		font-size: 12px;
		font-weight: 600;
	}
	.svg-help-btn {
		width: 18px;
		height: 18px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		background: var(--bg);
		color: var(--fg2);
		font: inherit;
		font-size: 11px;
		line-height: 1;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: 0 0 auto;
		padding: 0;
	}
	.svg-help-popover {
		width: min(480px, calc(100vw - 48px));
		padding: 12px;
		border-bottom: 1px solid var(--border);
		background: var(--bg2);
		color: var(--fg);
	}
	.svg-help-popover table {
		width: 100%;
		border-collapse: collapse;
		font-size: 11px;
		line-height: 1.45;
	}
	.svg-help-popover th,
	.svg-help-popover td {
		padding: 6px 8px;
		border: 1px solid var(--border);
		text-align: left;
		vertical-align: top;
	}
	.svg-help-popover th {
		background: var(--bg);
		color: var(--fg2);
		font-weight: 700;
		white-space: nowrap;
	}
	.svg-help-popover td:first-child {
		white-space: nowrap;
		font-weight: 600;
	}
	@media (max-width: 720px) {
		.instruction-caption {
			left: 10%;
			right: 10%;
			bottom: 58px;
			font-size: 13px;
		}
	}
	@keyframes spin { to { transform: rotate(360deg); } }
</style>
