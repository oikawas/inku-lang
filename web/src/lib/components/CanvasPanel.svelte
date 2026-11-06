<script lang="ts">
	import type { AutonomousRunsApi } from '$lib/features/autonomous/runs';
	import { tick } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import type { AnimationExportSettings } from '$lib/animationExport';
	import { modelShortName, type Provider, type ProviderGroup } from '$lib/models';
	import CanvasArtworkWorkspace from '$lib/features/canvas/CanvasArtworkWorkspace.svelte';
	import Ddl3DHost from '$lib/features/experimental-3d/Ddl3DHost.svelte';
	import Ddl3DModeSwitch from '$lib/features/experimental-3d/Ddl3DModeSwitch.svelte';
	import { configuredViewer } from '$lib/features/experimental-3d/input';
	import CanvasGenerationInfo from '$lib/features/canvas/CanvasGenerationInfo.svelte';
	import { pressChoosesWork } from '$lib/features/canvas/generation-info-follow';
	import { generationInfoSettings } from '$lib/features/canvas/generation-info-settings.svelte';
	import { ClipboardCopyRefused } from '$lib/clipboardExport';
	import CanvasPresentationOverlay from '$lib/features/canvas/CanvasPresentationOverlay.svelte';
	import CanvasRefinementWorkspace from '$lib/features/canvas/CanvasRefinementWorkspace.svelte';
	import type { LineageGraph, LineageNode } from '$lib/features/history/types';
	import type { HistoryMutations } from '$lib/features/history/mutations';
	import { normalizeSketchState, sketchStateNote, sketchStateShort, type SketchMode } from '$lib/sketch';
	import { drawOptionRows, INPUT_PANEL_ORDER } from '$lib/features/draw-options';
	import type { LineageBrowsingState } from '$lib/features/history/lineage-state.svelte';
	import { measureSvgWeight } from '$lib/svgWeight';
	import { formatCanvasCapacity, groupDigits } from '$lib/formatNumber';
	import { normalizeCaptionWritingMode, supportsVerticalCaption, type CaptionPosition, type CaptionWritingMode } from '$lib/captionWritingMode';
	import { drawerScrollToRestore, emptyDrawerScrollMemory, rememberDrawerScroll, type DrawerTab } from '$lib/drawerScroll';
	import type { createModelInspection } from '$lib/features/model-inspection/state.svelte';

	type ModelInspection = ReturnType<typeof createModelInspection>;
	import Tooltip from './Tooltip.svelte';
	import WorkActionMenu, { type WorkAction } from './WorkActionMenu.svelte';
	import WorkEditDialog from './WorkEditDialog.svelte';
	import JuxtaposeDialog from './JuxtaposeDialog.svelte';
	import type { JuxtapositionResult } from '$lib/features/juxtaposition/juxtaposition';
	import { composeFallbackReason, composeFallbackState, composeFallbackValue } from '$lib/composeFallback';
	import type { CanvasViewport } from '$lib/features/canvas/viewport-state.svelte';
	import type { PaintResult } from '$lib/features/run/current-work';
	import type { RangePreview } from '$lib/composition-ranges';
	import type { makeSavedWorkExportActions } from '$lib/features/export/saved-work-actions';
	import type { CanvasStatusHistoryItem as HistoryItem } from '$lib/features/canvas/view-types';
	import type { ProviderAttemptCount } from '$lib/paintStream';
	import type {
		RefinementSession,
		RefinementView,
		RefineKind
	} from '$lib/features/canvas/refinement-session.svelte';

	type OutputTab = 'canvas' | 'refine' | 'lineage';
	type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;
	type Props = {
		outputTab: OutputTab;
		libraryFocusRequest?: number;
		viewMode?: '2d' | '3d';
		result: PaintResult | null;
		rangePreview?: RangePreview | null;
		unsavedRefinementPreview: boolean;
		allowEmptyOutputTabs: boolean;
		currentRenderedAt: string | null;
		// The three nav buttons, each with its own answer. They come decided by
		// historyNavigation.ts so this panel and the strip read one judgement.
		navLatestDisabled: boolean;
		navNewerDisabled: boolean;
		navOlderDisabled: boolean;
		navOldestDisabled: boolean;
		// A demo is running, so nothing may move. ORed into every nav button
		// below as well: the flags above already carry it, and this is the guard
		// that stays if a caller ever forgets to pass it through them.
		interactionLocked: boolean;
		generationLocked: boolean;
		historyTotal: number;
		navPos: number;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		viewport: CanvasViewport;
		stage1PromptText: string;
		instructionText: string;
		ddl: string | null;
		copiedPrompt: 'sketch' | 'stage1' | 'composition' | 'laws' | 'colors' | 'reading' | 'stage2' | 'score' | null;
		scoreJsonText: string;
		scoreJsonLines: string[];
		scoreJsonHighlighted: string;
		scoreJsonSeparatorLine: number | null;
		statusStage1Model: string;
		statusStage2Model: string;
		statusStage1ModelOnly: string;
		statusStage2ModelOnly: string;
		/** The models a redraw started here calls: the page's choice, not the displayed work's. */
		runStage1ModelLabel: string;
		runStage2ModelLabel: string;
		visionModel: string;
		okugakiModel: string;
		visionProviderGroups: ProviderGroup[];
		statusCatalogName: string;
		statusCanvasName: string;
		statusGeneration: number | null;
		stageLabel: string;
		statusHistoryItem: HistoryItem | null;
		/** The work the star and revision marks act on: the status item, else a
		 *  just-saved result not yet in the history strip. */
		markHistoryItem: HistoryItem | null;
		statusHashLabel: string;
		statusHashCopied: boolean;
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
		onGotoOldest: () => void | Promise<void>;
		onCopyPromptText: (kind: 'sketch' | 'stage1' | 'composition' | 'laws' | 'colors' | 'reading' | 'stage2' | 'score', text: string | null | undefined) => void | Promise<void>;
		onCopyStatusHash: () => void | Promise<void>;
		onCopyWorkId: (workId: string) => void | Promise<void>;
		onSaveNote: HistoryMutations['saveNote'];
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
		singleUserMode?: boolean;
		onReplayCurrent: () => void | Promise<void>;
		replayDisabled: boolean;
		// The card is built from a saved work, so the toolbar needs its id, not
		// just the drawing on screen.
		currentHistoryId: string | null;
		savedWorkExportActions: ReturnType<typeof makeSavedWorkExportActions>;
		onDownloadCard: () => void | Promise<void>;
		/** Copy the work on the canvas to the clipboard as a bitmap; a refusal throws ClipboardCopyRefused. */
		onCopyToClipboard: () => Promise<void>;
		instructionCaptionVisible: boolean;
		onInstructionCaptionVisibleChange: (visible: boolean) => void | Promise<void>;
		instructionCaptionWritingMode: CaptionWritingMode;
		onInstructionCaptionWritingModeChange: (mode: CaptionWritingMode) => void | Promise<void>;
		instructionCaptionPosition: CaptionPosition;
		refinementSession: RefinementSession;
		runTokensIn: number | null;
		runTokensOut: number | null;
		runAttempt?: ProviderAttemptCount | null;
		runProgress?: import('$lib/paintStream').PaintProgressEvent | null;
		/** The whole feature, so a new field costs no line here. */
		modelInspection: ModelInspection;
		onGenerateVariationCandidates: (kind: RefineKind, count: 1 | 4) => void | Promise<void>;
		onGenerateColorCatalogCandidates: () => void | Promise<void>;
		onGenerateColorArrangementCandidates: () => void | Promise<void>;
		onGenerateGroundCandidates: () => void | Promise<void>;
		onGenerateCompositionFormCandidates: (form: import('$lib/features/canvas/composition-form').CompositionForm, count: 1 | 4) => void | Promise<void>;
		onGenerateToolCandidates: () => void | Promise<void>;
		/** Draws the work with each model picked in the "change the model" dialog. */
		onGenerateModelCandidates: () => void | Promise<void>;
		/** True when every chosen option is now in the history. */
		onSaveSelectedVariationCandidates: () => Promise<boolean>;
		lineageGraph: LineageGraph | null;
		lineageBrowsingState: LineageBrowsingState;
		lineageLoading: boolean;
		lineageError: string | null;
		isJapanese: boolean;
		onOpenLineageNode: (node: LineageNode) => void | Promise<void>;
		onOpenLineageNodeInCanvas: (node: LineageNode) => void | Promise<void>;
		onResolveCurrentLineageNode: () => Promise<LineageNode | null>;
		onFocusLatestRefinementChild: (parentNodeId: string, knownChildNodeIds: Set<string>) => boolean | Promise<boolean>;
		onToggleLineageStar: (node: LineageNode, event?: Event) => void | Promise<void>;
		onToggleLineageForRevision: (node: LineageNode, event?: Event) => void | Promise<void>;
		onDrawLineageDescription: (node: LineageNode, text: string, signal?: AbortSignal, wild?: boolean | null, metadata?: Record<string, unknown>) => void | Promise<void>;
		onOpenLineageDdlEditor: (node: LineageNode) => void;
		onDrawLineageSketchGrain: (node: LineageNode, mode: SketchMode, signal?: AbortSignal) => Promise<void>;
		onToggleSaijiki: () => void;
		onCloseRefinement: () => void;
		statusDdlOrigin: boolean;
		statusDescriptionLocked: boolean;
		developerMode: boolean;
		// The staffage level a work was drawn at, for works saved before the axis
		// was folded away (v2.11.0). Developer mode only, and only when set.
		statusTenkei: string | null;
		// The model comparison's stroke limit switch. The layout options draw with
		// the input panel's model and stroke limit (2026-11-06, the author).
		refineWildValue: boolean;
		onSetRefineWild: (value: boolean | null) => void;
		onSaveOkugakiModel: (provider: Provider, model: string) => void | Promise<void>;
		onSaveVisionModel: (provider: Provider, model: string) => void | Promise<void>;
		onSaveLineageNote: (node: LineageNode, note: string) => void | Promise<void>;
		onAskTrashLineage: (historyIds: string[]) => void;
		onDetachLineage: () => void;
		onLoadLineageOverview: () => void | Promise<void>;
		onLoadLineageBranch: (nodeId: string) => void | Promise<void>;
		/** The AI refinement's runs, which the Server takes (2026-10-21). */
		autonomousRuns: AutonomousRunsApi;
		/** Open a child an AI refinement run kept. */
		onOpenAutonomousChild: (historyId: string, nodeId: string | null) => void | Promise<void>;
		onJuxtapose: (historyId: string, model: string, exclude: string[], signal: AbortSignal) => Promise<JuxtapositionResult>;
	};

	let {
		outputTab = $bindable('canvas'),
		viewMode = $bindable('2d'),
		result,
		rangePreview = null,
		unsavedRefinementPreview = false,
		allowEmptyOutputTabs,
		currentRenderedAt,
		navLatestDisabled,
		navNewerDisabled,
		navOlderDisabled,
		navOldestDisabled,
		interactionLocked,
		generationLocked,
		historyTotal,
		navPos,
		canvasAspectWidth = 1,
		canvasAspectHeight = 1,
		viewport,
		stage1PromptText,
		instructionText,
		ddl,
		copiedPrompt,
		scoreJsonText,
		scoreJsonLines,
		scoreJsonHighlighted,
		scoreJsonSeparatorLine,
		statusStage1Model,
		statusStage2Model,
		statusStage1ModelOnly,
		statusStage2ModelOnly,
		runStage1ModelLabel,
		runStage2ModelLabel,
		visionModel,
		okugakiModel,
		visionProviderGroups,
		statusCatalogName,
		statusCanvasName,
		statusGeneration,
		stageLabel,
		statusHistoryItem,
		markHistoryItem,
		statusHashLabel,
		statusHashCopied,
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
		onGotoOldest,
		onCopyPromptText,
		onCopyStatusHash,
		onCopyWorkId,
		onSaveNote,
		onToggleStar,
		onToggleForRevision,
		onToggleForShare = null,
		singleUserMode = false,
		onReplayCurrent,
		replayDisabled,
		currentHistoryId,
		savedWorkExportActions,
		onDownloadCard,
		onCopyToClipboard,
		instructionCaptionVisible = $bindable(true),
		onInstructionCaptionVisibleChange,
		instructionCaptionWritingMode,
		onInstructionCaptionWritingModeChange,
		instructionCaptionPosition,
		refinementSession,
		runTokensIn = null,
		runTokensOut = null,
		runAttempt = null,
		runProgress = null,
		modelInspection,
		onGenerateVariationCandidates,
		onGenerateColorCatalogCandidates,
		onGenerateColorArrangementCandidates,
		onGenerateGroundCandidates,
		onGenerateCompositionFormCandidates,
		onGenerateToolCandidates,
		onGenerateModelCandidates,
		onSaveSelectedVariationCandidates,
		lineageGraph = null,
		libraryFocusRequest = 0,
		lineageBrowsingState,
		lineageLoading = false,
		lineageError = null,
		isJapanese = true,
		onOpenLineageNode,
		onOpenLineageNodeInCanvas,
		onResolveCurrentLineageNode,
		onFocusLatestRefinementChild,
		onToggleLineageStar,
		onToggleLineageForRevision,
		onDrawLineageDescription,
		onOpenLineageDdlEditor,
		onDrawLineageSketchGrain,
		onToggleSaijiki,
		onCloseRefinement,
		statusDdlOrigin,
		statusDescriptionLocked,
		developerMode,
		statusTenkei,
		refineWildValue,
		onSetRefineWild,
		onSaveOkugakiModel,
		onSaveVisionModel,
		onSaveLineageNote,
		onAskTrashLineage,
		onDetachLineage,
		onLoadLineageOverview,
		onLoadLineageBranch,
		autonomousRuns,
		onOpenAutonomousChild,
		onJuxtapose
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

	// What the clipboard button last did, said in its tooltip: busy while the
	// picture is made, then "copied" for a moment, or the reason it could not.
	let clipboardBusy = $state(false);
	let clipboardMessage = $state<string | null>(null);
	let clipboardMessageTimer: ReturnType<typeof setTimeout> | null = null;

	async function copyToClipboardFromCanvas(): Promise<void> {
		if (clipboardBusy) return;
		clipboardBusy = true;
		if (clipboardMessageTimer) clearTimeout(clipboardMessageTimer);
		try {
			await onCopyToClipboard();
			clipboardMessage = t().canvasCopiedToClipboard;
			clipboardMessageTimer = setTimeout(() => (clipboardMessage = null), 2500);
		} catch (error) {
			// A browser or server failure reads as a DOMException name or a
			// status; the author is better served by the plain sentence.
			clipboardMessage = error instanceof ClipboardCopyRefused ? error.message : t().clipboardCopyFailed;
			clipboardMessageTimer = setTimeout(() => (clipboardMessage = null), 8000);
		} finally {
			clipboardBusy = false;
		}
	}

	async function downloadCardFromCanvas(): Promise<void> {
		if (cardExportBusy) return;
		cardExportBusy = true;
		try {
			await onDownloadCard();
		} finally {
			cardExportBusy = false;
		}
	}
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
	let refineView = $state<RefinementView>('layout');
	let refineModalOpen = $state(false);
	let refineReturnTab = $state<OutputTab>('lineage');
	let directRefinementActive = $state(false);
	let directRefinementSaveObserved = $state(false);
	let directRefinementParentNodeId = $state<string | null>(null);
	let directRefinementKnownChildNodeIds = $state<Set<string>>(new Set());
	let directRefinementSavedCandidateIds = $state<Set<string>>(new Set());
	let directActionNode = $state<LineageNode | null>(null);
	let directActionMenuOpen = $state(false);
	let directEditNode = $state<LineageNode | null>(null);
	let directEditMode = $state<'description' | 'sketch-grain' | null>(null);
	let directAIRefineNode = $state<LineageNode | null>(null);
	let directJuxtaposeNode = $state<LineageNode | null>(null);
	// A result just saved is not in the history list yet, so its generation is
	// not known for a moment; it is not called standalone meanwhile.
	const statusGenerationPending = $derived(!statusHistoryItem && !!result?.history_id);
	const statusGenerationValue = $derived(
		statusGeneration
			? (isJapanese ? `第${statusGeneration}世代` : `Gen. ${statusGeneration}`)
			: statusGenerationPending ? '…'
				: (isJapanese ? '独立作品' : 'Standalone')
	);
	const statusWork = $derived(statusHistoryItem ?? result);
	// One source for the strip: the saved work on screen, else the result on
	// screen (a finished run carries its recorded choices before the history
	// list is read again, and during a run the previous picture keeps its own).
	const stripOptions = $derived(statusHistoryItem?.draw_options ?? result?.draw_options ?? null);
	const stripIsImage = $derived(!!stripOptions?.models?.vision || !!(statusWork?.image_ddl));
	const statusSketchState = $derived(normalizeSketchState(statusHistoryItem?.sketch_state ?? result?.sketch_state));
	// How the work on screen was drawn and what its sketch did, from the saved
	// work when there is one, as the generation information reads them.
	async function openLineageRefinement(node: LineageNode, view: RefinementView): Promise<void> {
		await onOpenLineageNode(node);
		onSetRefineWild(null);
		refineView = view;
		refineReturnTab = 'lineage';
		directRefinementActive = false;
		directRefinementParentNodeId = null;
		refineModalOpen = true;
		outputTab = 'refine';
		if (view === 'color') void onGenerateColorCatalogCandidates();
		if (view === 'color-arrangement') void onGenerateColorArrangementCandidates();
		if (view === 'ground') void onGenerateGroundCandidates();
	}

	let canvasAreaEl: HTMLDivElement | null = null;

	export async function focusCurrentWork(): Promise<void> {
		await tick();
		canvasAreaEl?.focus({ preventScroll: true });
	}

	export async function openDirectActionMenu(): Promise<void> {
		if (interactionLocked || generationLocked) return;
		const historyId = currentHistoryId;
		if (!historyId) return;
		const node = await onResolveCurrentLineageNode();
		if (currentHistoryId !== historyId) return;
		directActionNode = node;
		directActionMenuOpen = !!node;
	}

	function startDirectRefinement(node: LineageNode, view: RefinementView): void {
		onSetRefineWild(null);
		refineView = view;
		refineReturnTab = 'canvas';
		directRefinementActive = true;
		directRefinementSaveObserved = false;
		directRefinementParentNodeId = node.id;
		directRefinementKnownChildNodeIds = new Set(
			lineageGraph?.edges.filter((edge) => edge.parent_node_id === node.id).map((edge) => edge.child_node_id)
		);
		directRefinementSavedCandidateIds = new Set(
			refinementSession.candidates.filter((candidate) => candidate.saved).map((candidate) => candidate.id)
		);
		refineModalOpen = true;
		outputTab = 'refine';
		if (view === 'color') void onGenerateColorCatalogCandidates();
		if (view === 'color-arrangement') void onGenerateColorArrangementCandidates();
		if (view === 'ground') void onGenerateGroundCandidates();
	}

	function openDirectEdit(node: LineageNode, mode: 'description' | 'sketch-grain'): void {
		directEditNode = node;
		directEditMode = mode;
	}

	function closeDirectEdit(): void {
		directEditNode = null;
		directEditMode = null;
	}

	async function runDirectWorkAction(action: WorkAction, node: LineageNode): Promise<void> {
		switch (action) {
			case 'layout': startDirectRefinement(node, 'layout'); break;
			case 'color-catalog': startDirectRefinement(node, 'color'); break;
			case 'color-arrangement': startDirectRefinement(node, 'color-arrangement'); break;
			case 'ground': startDirectRefinement(node, 'ground'); break;
			case 'tool': startDirectRefinement(node, 'tool'); break;
			case 'description': openDirectEdit(node, 'description'); break;
			case 'instructions': onOpenLineageDdlEditor(node); break;
			case 'sketch-grain': openDirectEdit(node, 'sketch-grain'); break;
			case 'models':
				startDirectRefinement(node, 'compare');
				break;
			case 'composition-form': startDirectRefinement(node, 'composition-form'); break;
			case 'juxtapose': directJuxtaposeNode = node; break;
			case 'autonomous': directAIRefineNode = node; break;
		}
	}

	// Unsaved options pin the dialog open: it is left only by saving the
	// chosen ones or discarding them all, so no unsaved work stays behind
	// while another screen is shown.
	function requestCloseRefineModal(): void {
		if (refinementSession.hasUnsaved) {
			refinementSession.setStatus(t().refineCloseNeedsDecision);
			return;
		}
		void closeRefineModal();
	}

	async function saveCandidatesAndClose(): Promise<void> {
		if (!(await onSaveSelectedVariationCandidates())) return;
		// The save effect below may not have run yet; the lineage focus on
		// close needs to know that something was saved.
		if (directRefinementActive) directRefinementSaveObserved = true;
		refinementSession.discardCandidates();
		await closeRefineModal();
	}

	async function discardCandidatesAndClose(): Promise<void> {
		refinementSession.discardCandidates();
		await closeRefineModal();
	}

	async function closeRefineModal(): Promise<void> {
		refineModalOpen = false;
		const savedParentNodeId = directRefinementActive && directRefinementSaveObserved ? directRefinementParentNodeId : null;
		const knownChildNodeIds = directRefinementKnownChildNodeIds;
		directRefinementActive = false;
		directRefinementParentNodeId = null;
		// Reflect any adopted comparison/variation results into the lineage tree.
		if (savedParentNodeId && await onFocusLatestRefinementChild(savedParentNodeId, knownChildNodeIds)) {
			outputTab = 'lineage';
		} else {
			outputTab = refineReturnTab;
			onCloseRefinement();
		}
	}

	$effect(() => {
		if (!directRefinementActive) return;
		const savedCandidate = refinementSession.candidates.some((candidate) => candidate.saved && !directRefinementSavedCandidateIds.has(candidate.id));
		if (savedCandidate) directRefinementSaveObserved = true;
	});

	$effect(() => {
		currentHistoryId;
		directActionNode = null;
		directActionMenuOpen = false;
	});

	const canvasMaxRatio = $derived(Math.max(canvasAspectWidth, canvasAspectHeight, 1));
	const ddl3dViewer = configuredViewer(import.meta.env.VITE_DDL_3D_VIEWER_URL);
	const canvasBaseWidth = $derived(400 * canvasAspectWidth / canvasMaxRatio);
	let ddl3dZoom = $state(1);
	let ddl3dCommand = $state<{ id: number; action: 'zoom' | 'reset'; value?: number }>();
	const ddl3dActive = $derived(viewMode === '3d' && !!ddl3dViewer && !!result);
	const ddl3dZoomControls = {
		get zoom() { return ddl3dZoom; },
		setZoom(value: number) { ddl3dCommand = { id: (ddl3dCommand?.id ?? 0) + 1, action: 'zoom', value: Math.max(0.25, Math.min(10, value)) }; },
		fit() { ddl3dCommand = { id: (ddl3dCommand?.id ?? 0) + 1, action: 'reset' }; }
	};
	const canvasBaseHeight = $derived(400 * canvasAspectHeight / canvasMaxRatio);
	const displayInstructionText = $derived((instructionText || '').trim());
	const canShowInstructionCaption = $derived(!!displayInstructionText);
	const canUseVerticalInstructionCaption = $derived(supportsVerticalCaption(displayInstructionText));
	const instructionCaptionVertical = $derived(
		instructionCaptionWritingMode === 'vertical' && canUseVerticalInstructionCaption
	);

	function toggleInstructionCaption() {
		instructionCaptionVisible = !instructionCaptionVisible;
		void onInstructionCaptionVisibleChange(instructionCaptionVisible);
	}

	function setInstructionCaptionWritingMode(event: Event): void {
		const mode = normalizeCaptionWritingMode((event.currentTarget as HTMLSelectElement).value);
		void onInstructionCaptionWritingModeChange(mode);
	}

	function updateFitZoom() {
		if (!canvasContentEl || viewMode === '3d') return;
		const rect = canvasContentEl.getBoundingClientRect();
		const availableWidth = Math.max(120, rect.width - 120);
		const availableHeight = Math.max(120, rect.height - 96);
		const nextZoom = Math.max(0.25, Math.min(10, Math.min(availableWidth / canvasBaseWidth, availableHeight / canvasBaseHeight)));
		viewport.updateFitZoom(+nextZoom.toFixed(2));
	}

	$effect(() => {
		const wheelTarget = canvasContentEl;
		if (!wheelTarget || viewMode === '3d') return;
		updateFitZoom();
		const observer = new ResizeObserver(updateFitZoom);
		observer.observe(wheelTarget);
		const onWheel = (event: WheelEvent) => {
			if (outputTab !== 'canvas' || viewMode === '3d' || !result) return;
			// A menu over the canvas (the export menu) scrolls itself; the wheel is not a zoom there.
			if (event.target instanceof Element && event.target.closest('.instruction-caption.vertical, .canvas-caption-writing-mode, [role="menu"]')) return;
			event.preventDefault();
			const step = event.deltaY < 0 ? 0.15 : -0.15;
			viewport.setZoom(viewport.zoom + step);
		};
		wheelTarget.addEventListener('wheel', onWheel, { passive: false });
		return () => {
			observer.disconnect();
			wheelTarget.removeEventListener('wheel', onWheel);
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
	// The strip needs bytes alone; the drawer counts structure when opened.
	const detailSvgWeight = $derived(generationInfoOpen && result?.svg ? measureSvgWeight(result.svg) : null);
	const detailSvgBytes = $derived(result?.svg ? new TextEncoder().encode(result.svg).length : null);
	const canvasNavOldestTooltip = $derived(t().tooltipCanvasNavOldest);
</script>

<svelte:window
	onbeforeunload={(event) => {
		// Reloading or closing the tab would lose them just the same.
		if (refinementSession.hasUnsaved) event.preventDefault();
	}}
	onkeydown={(event) => {
		if (event.key !== 'Escape') return;
		if (refineModalOpen) requestCloseRefineModal();
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
		// Choosing another work from the history strip keeps the drawer open
		// when the setting says so; the drawer reads the work on the canvas,
		// so it shows the chosen one once it is loaded.
		if (generationInfoSettings.followsSelection && target instanceof Element && pressChoosesWork(target)) return;
		closeGenerationInfo();
	}}
/>

<div class="right-panel">
	<!-- One row: the tabs, which are pressed, then the displayed work's
	     conditions, which are only read. The tabs stand the row's full height on
	     an accent underline like the input panel's tabs; the conditions are bare
	     text past a rule, with no frame, fill or hover, in the input panel's
	     top-to-bottom order. The work's actions stand over the canvas's top
	     right instead (the author, 2026-11-05). -->
	<div class="right-tabs">
		<div class="rtab-group" role="tablist">
			<Tooltip placement="bottom-right" text={t().tooltipCanvasTabCanvas}>
				<button class="rtab" role="tab" aria-selected={outputTab === 'canvas'} class:active={outputTab === 'canvas'} onclick={() => (outputTab = 'canvas')}>{t().tabCanvas}</button>
			</Tooltip>
			<Tooltip placement="bottom" text={isJapanese ? '作品の派生関係を表示' : 'Show how this work was derived'}>
				<button class="rtab" role="tab" aria-selected={outputTab === 'lineage'} class:active={outputTab === 'lineage'} onclick={() => (outputTab = 'lineage')} disabled={!result}>{isJapanese ? '系譜' : 'Lineage'}</button>
			</Tooltip>
		</div>
		{#if result}
			<div class="render-meta-strip" role="group" aria-label={t().displayedWorkConditions}>
				<div class="render-meta-context">
					<span class="render-meta-heading">{t().displayedWorkConditions}</span>
					<span class="render-meta-generation">
						{#if statusGeneration || statusGenerationPending}<span class="render-meta-label">{isJapanese ? '系譜' : 'Lineage'}</span>{/if}
						<strong>{statusGenerationValue}</strong>
					</span>
				</div>
				<div class="render-meta-fields">
					{#each drawOptionRows(stripOptions, t(), { image: stripIsImage, order: INPUT_PANEL_ORDER }) as option (option.key)}
						<span class="render-meta-item" data-draw-option={option.key}>
							<span class="render-meta-label">{option.label}</span>
							{#if option.key === 'models' && stripOptions?.models && (stripOptions.models.vision || stripOptions.models.stage1 || stripOptions.models.stage2)}
								<strong title={statusStage1Model + ' / ' + statusStage2Model}>
									{#if stripOptions.models.vision}
										<span class="render-meta-model-line"><span class="render-meta-model-name">{modelShortName(stripOptions.models.vision)}</span></span>
									{:else if stripOptions.models.stage1 === stripOptions.models.stage2}
										<span class="render-meta-model-line"><span class="render-meta-model-name">{statusStage1ModelOnly}</span></span>
									{:else}
										<span class="render-meta-model-line"><span class="render-meta-model-stage">{t().drawOptionsStage1Short}</span><span class="render-meta-model-name">{statusStage1ModelOnly}</span></span>
										<span class="render-meta-model-line"><span class="render-meta-model-stage">{t().drawOptionsStage2Short}</span><span class="render-meta-model-name">{statusStage2ModelOnly}</span></span>
									{/if}
								</strong>
							{:else if option.key === 'catalog' && stripOptions?.catalog}
								{@const catalog = stripOptions.catalog}
								<strong title={statusCatalogName}>{catalog.id ? statusCatalogName : t().drawOptionsUnavailable} ({catalog.mode === 'auto' ? t().colorCatalogAuto : catalog.mode === 'fixed' ? t().drawDefaultsFixed : t().drawOptionsUnavailable})</strong>
							{:else if option.key === 'canvas_aspect' && stripOptions?.canvas_aspect}
								<strong title={statusCanvasName}>{statusCanvasName}</strong>
							{:else if option.key === 'sketch' && stripOptions?.sketch}
								<strong title={`${sketchStateNote(statusSketchState, isJapanese) || sketchStateShort(statusSketchState, isJapanese)} — ${option.text}`}>{sketchStateShort(statusSketchState, isJapanese)} ({option.text})</strong>
							{:else}
								<strong title={option.text}>{option.text}</strong>
							{/if}
						</span>
					{/each}
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
			</div>
		{/if}
	</div>

	<!-- The work's actions over the canvas's top right, on the Work tab only:
	     the lineage tab gives every node its own. -->
	{#snippet workActions()}
		{#if currentHistoryId}
			<div class="canvas-work-actions">
				<WorkActionMenu
					node={directActionNode}
					{isJapanese}
					variant="header"
					open={directActionMenuOpen}
					available={!interactionLocked && !generationLocked}
					unavailableReason={t().workActionGenerationLocked}
					onRequestOpen={openDirectActionMenu}
					onOpenChange={(open) => (directActionMenuOpen = open)}
					onAction={runDirectWorkAction}
				/>
			</div>
		{:else if result && !generationLocked}
			<span class="canvas-work-actions work-action-save-first" role="status">{t().workActionSaveFirst}</span>
		{/if}
	{/snippet}
	{#snippet modeControl()}
		{#if ddl3dViewer && result}
			<Ddl3DModeSwitch bind:viewMode />
		{/if}
	{/snippet}
	{#snippet threeDimensionalContent()}
		{#if ddl3dViewer && result}
			<Ddl3DHost {result} viewerUrl={ddl3dViewer} {isJapanese} onReturn={() => (viewMode = '2d')}
				initialView={{ pixelWidth: canvasBaseWidth * viewport.actualZoom, pixelHeight: canvasBaseHeight * viewport.actualZoom, panX: viewport.panX, panY: viewport.panY, zoom: viewport.zoom }}
				command={ddl3dCommand} onViewState={(state) => { ddl3dZoom = state.displayZoom ?? 1; }} />
		{/if}
	{/snippet}

	<div class="canvas-area" bind:this={canvasAreaEl} tabindex="-1">
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
				leadingCornerControls={modeControl}
				topRightControls={workActions}
				artworkContent={ddl3dActive ? threeDimensionalContent : undefined}
				zoomControls={ddl3dActive ? ddl3dZoomControls : undefined}
				savedWorkExport={currentHistoryId && !statusHistoryItem?.trashed ? {
					scope: { kind: 'current', works: [{
						id: currentHistoryId,
						at: statusHistoryItem?.at ?? result?.history_at ?? 0,
						preview: result?.svg,
						description: instructionText
					}] },
					animationSettings: animationExportSettings,
					pngTemplates,
					...savedWorkExportActions
				} : null}
				{result}
				{rangePreview}
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
				{instructionCaptionVisible}
				{canShowInstructionCaption}
				{displayInstructionText}
				{instructionCaptionWritingMode}
				{instructionCaptionPosition}
				{canUseVerticalInstructionCaption}
				{instructionCaptionVertical}
				statusHistoryItem={markHistoryItem}
				{replayDisabled}
				{allowEmptyOutputTabs}
				{generationInfoOpen}
				bind:generationInfoToggleEl
				{exportCardOnly}
				{cardExportBusy}
				{currentHistoryId}
				{isJapanese}
				onToggleInstructionCaption={toggleInstructionCaption}
				onInstructionCaptionWritingModeChange={setInstructionCaptionWritingMode}
				{onToggleStar}
				{onToggleForRevision}
				{onToggleForShare}
				{singleUserMode}
				{onCopyWorkId}
				{onReplayCurrent}
				onToggleGenerationInfo={() => (generationInfoOpen ? closeGenerationInfo() : openGenerationInfo())}
				{onToggleSaijiki}
				onDownloadCard={downloadCardFromCanvas}
				{clipboardBusy}
				{clipboardMessage}
				onCopyToClipboard={copyToClipboardFromCanvas}
				onOpenPresentation={() => { if (ddl3dActive) void canvasAreaEl?.requestFullscreen(); else presentationMode = true; }}
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
					{statusDescriptionLocked}
					compositionForm={statusWork?.description_ddl?.composition?.answer?.form ?? null}
					compositionFormSwitch={!statusWork?.description_ddl?.composition}
					{statusStage1Model}
					{statusStage2Model}
					{refineWildValue}
					onClose={requestCloseRefineModal}
					{onGenerateVariationCandidates}
					{onGenerateColorCatalogCandidates}
					{onGenerateColorArrangementCandidates}
					{onGenerateGroundCandidates}
					{onGenerateCompositionFormCandidates}
					{onGenerateToolCandidates}
					{onGenerateModelCandidates}
					catalogName={statusCatalogName}
					onSaveAndClose={saveCandidatesAndClose}
					onDiscardAndClose={discardCandidatesAndClose}
					{onSetRefineWild}
				/>
			{:else if outputTab === 'lineage'}
				{#await import('./LineagePanel.svelte') then { default: LineagePanel }}
					<LineagePanel browsingState={lineageBrowsingState} graph={lineageGraph} loading={lineageLoading} error={lineageError} focusRequest={libraryFocusRequest}
						{isJapanese} onOpenNode={onOpenLineageNode}
						onOpenNodeInCanvas={onOpenLineageNodeInCanvas} onToggleStar={onToggleLineageStar}
						onToggleForRevision={onToggleLineageForRevision} onOpenRefinement={openLineageRefinement}
						onDrawDescription={onDrawLineageDescription} onOpenDdlEditor={onOpenLineageDdlEditor}
						onDrawSketchGrain={onDrawLineageSketchGrain} {stageLabel} stage1ModelLabel={runStage1ModelLabel}
						stage2ModelLabel={runStage2ModelLabel} {runTokensIn} {runTokensOut} {runAttempt} {runProgress} onSaveOkugakiModel={onSaveOkugakiModel}
						{onSaveVisionModel} onSaveNote={onSaveLineageNote}
						onAskTrash={onAskTrashLineage} onDetach={onDetachLineage} onLoadOverview={onLoadLineageOverview}
						onLoadBranch={onLoadLineageBranch} {autonomousRuns} {onOpenAutonomousChild} {onJuxtapose} {visionModel} {okugakiModel}
						{visionProviderGroups} {animationExportSettings} {pngTemplates}
						onDownloadSavedWorkSVG={savedWorkExportActions.onDownloadSVG}
						onDownloadSavedWorkPNG={savedWorkExportActions.onDownloadPNG}
						onDownloadSavedWorkCard={savedWorkExportActions.onDownloadCard}
						onDownloadSavedWorkDdl={savedWorkExportActions.onDownloadDdl}
						onDownloadSavedWorkAnimation={savedWorkExportActions.onDownloadAnimation}
						onDownloadSavedWorkContactSheet={savedWorkExportActions.onDownloadContactSheet}
						onValidateSavedWorkExport={savedWorkExportActions.onValidateSnapshot} />
				{/await}
			{/if}
		</div>
		{/if}



		<div class="nav-right">
			<Tooltip placement="left" text={canvasNavOldestTooltip}>
				<button class="nav-latest" onclick={() => onGotoOldest()} disabled={interactionLocked || navOldestDisabled}>{t().historyOldest}</button>
			</Tooltip>
			<Tooltip placement="left" text={t().tooltipCanvasNavOlder}>
				<button class="nav-circle" onclick={onGotoPrev} disabled={interactionLocked || navOlderDisabled}>›</button>
			</Tooltip>
			{#if historyTotal > 0}
				<span class="nav-counter">{groupDigits(navPos)} / {groupDigits(historyTotal)}</span>
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
		workId={unsavedRefinementPreview ? null : currentHistoryId}
		{interactionLocked}
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
		{stage1PromptText}
		{ddl}
		{copiedPrompt}
		{scoreJsonText}
		{scoreJsonLines}
		{scoreJsonHighlighted}
		{scoreJsonSeparatorLine}
		onClose={closeGenerationInfo}
		{onSaveNote}
		{onCopyWorkId}
		{onCopyStatusHash}
		{onCopyPromptText}
	/>


</div>

{#if directEditNode && directEditMode}
	<WorkEditDialog
		node={directEditNode}
		mode={directEditMode}
		{isJapanese}
		{stageLabel}
		stage1ModelLabel={runStage1ModelLabel}
		stage2ModelLabel={runStage2ModelLabel}
		tokensIn={runTokensIn}
		tokensOut={runTokensOut}
		attempt={runAttempt}
		progress={runProgress}
		onClose={closeDirectEdit}
		onDrawDescription={onDrawLineageDescription}
		onDrawSketchGrain={onDrawLineageSketchGrain}
	/>
{/if}

{#if directJuxtaposeNode}
	<JuxtaposeDialog
		node={directJuxtaposeNode}
		{visionModel}
		{visionProviderGroups}
		{stageLabel}
		stage1ModelLabel={runStage1ModelLabel}
		stage2ModelLabel={runStage2ModelLabel}
		tokensIn={runTokensIn}
		tokensOut={runTokensOut}
		attempt={runAttempt}
		progress={runProgress}
		onClose={() => (directJuxtaposeNode = null)}
		{onSaveVisionModel}
		{onJuxtapose}
		onDrawDescription={onDrawLineageDescription}
	/>
{/if}

{#if directAIRefineNode}
	{#await import('./AIRefineModal.svelte') then { default: AIRefineModal }}
		<AIRefineModal
			node={directAIRefineNode}
			onClose={() => (directAIRefineNode = null)}
			{autonomousRuns}
			onOpenChild={onOpenAutonomousChild}
			{onSaveVisionModel}
			{visionModel}
			{visionProviderGroups}
		/>
	{/await}
{/if}

{#if presentationMode && result}
	<CanvasPresentationOverlay
		{artworkUrl}
		{instructionCaptionVisible}
		{canShowInstructionCaption}
		{displayInstructionText}
		{instructionCaptionWritingMode}
		{instructionCaptionPosition}
		{canUseVerticalInstructionCaption}
		{instructionCaptionVertical}
		{interactionLocked}
		{navNewerDisabled}
		{navLatestDisabled}
		{navOlderDisabled}
		{historyTotal}
		{navPos}
		workMark={markHistoryItem}
		{onGotoNext}
		{onGotoLatest}
		{onGotoPrev}
		onToggleStar={(event) => onToggleStar(markHistoryItem, event)}
		onToggleCaption={toggleInstructionCaption}
		onInstructionCaptionWritingModeChange={setInstructionCaptionWritingMode}
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
		container: canvas-panel / inline-size;
		overflow: hidden;
	}
	.right-tabs {
		display: flex;
		align-items: stretch;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		padding: 0 16px;
		flex-shrink: 0;
	}
	/* The tabs stand the row's full height, so their underline sits on the
	   row's rule however many lines the conditions beside them take. */
	.rtab-group { display: flex; align-items: stretch; flex: 0 0 auto; }
	.rtab-group > :global(.tooltip-wrap) { display: flex; align-items: stretch; }
	.rtab {
		display: flex;
		align-items: center;
		padding: 9px 16px;
		border: none;
		border-bottom: 2px solid transparent;
		border-radius: 6px 6px 0 0;
		margin-bottom: -1px;
		background: none;
		color: var(--fg2);
		font-size: var(--ui-font-size-13);
		cursor: pointer;
		font-family: inherit;
		white-space: nowrap;
	}
	.rtab.active { border-bottom-color: var(--accent); color: var(--fg); font-weight: 500; }
	.rtab:hover:not(.active):not(:disabled) { color: var(--fg); background: var(--bg2); }
	.rtab:disabled { opacity: 0.35; cursor: not-allowed; }
	/* Read only: bare text past a rule, with no frame, fill, underline or
	   hover, set smaller than the tabs. It takes the rest of the tabs' row and
	   its items wrap whole, so no label overlaps another at any width or text
	   size. */
	.render-meta-strip {
		display: flex;
		align-items: center;
		gap: 14px;
		flex: 1 1 0;
		min-width: 0;
		margin-left: 16px;
		padding: 5px 0 5px 16px;
		border-left: 1px solid var(--border);
		color: var(--fg3);
		cursor: default;
	}
	.render-meta-context {
		display: flex;
		flex-direction: column;
		gap: 1px;
		flex: 0 0 auto;
	}
	.render-meta-heading {
		color: var(--fg3);
		font-size: var(--ui-font-size-11);
		line-height: 1.5;
		white-space: nowrap;
	}
	.render-meta-generation {
		display: flex;
		align-items: baseline;
		gap: 5px;
		white-space: nowrap;
	}
	.render-meta-generation strong { color: var(--fg2); font-size: var(--ui-font-size-12); font-weight: 450; line-height: 1.5; }
	.render-meta-fields {
		display: flex;
		flex-wrap: wrap;
		column-gap: 14px;
		row-gap: 1px;
		flex: 1 1 0;
		min-width: 0;
	}
	.render-meta-item {
		display: inline-flex;
		align-items: baseline;
		gap: 5px;
		flex: 0 1 auto;
		min-width: 0;
		max-width: calc(280px * var(--ui-text-scale));
	}
	.render-meta-label {
		color: var(--fg3);
		font-size: var(--ui-font-size-11);
		line-height: 1.5;
		white-space: nowrap;
	}
	.render-meta-item strong {
		min-width: 0;
		max-width: 100%;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--fg2);
		font-size: var(--ui-font-size-12);
		font-weight: 450;
		line-height: 1.5;
		white-space: nowrap;
	}
	/* The two numeric items: never ellipsised, and set on the digit grid so a
	   size and a timestamp do not jitter as the work on screen changes. */
	.render-meta-created,
	.render-meta-svg-size { flex: 0 0 auto; max-width: none; }
	.render-meta-created strong,
	.render-meta-svg-size strong {
		max-width: none;
		font-variant-numeric: tabular-nums;
	}
	/* A work drawn with two models names both stages on one line. */
	.render-meta-item strong:has(.render-meta-model-line) { display: inline-flex; gap: 8px; }
	.render-meta-model-line { display: flex; gap: 4px; min-width: 0; white-space: nowrap; }
	.render-meta-model-stage { flex: 0 0 auto; color: var(--fg3); }
	.render-meta-model-name { min-width: 0; overflow: hidden; text-overflow: ellipsis; }
	/* Over the artwork, so the note reads on a pill of its own and the menu's
	   trigger keeps an opaque face (its border and hover are the menu's). */
	.canvas-work-actions :global(.work-action-trigger) { background: var(--bg); box-shadow: 0 2px 10px #0002; }
	.work-action-save-first {
		padding: 5px 9px;
		border: 1px solid var(--border2);
		border-radius: 999px;
		background: color-mix(in srgb, var(--panel) 94%, transparent);
		box-shadow: 0 2px 10px #0002;
		color: var(--fg3);
		font-size: var(--ui-font-size-11);
		white-space: nowrap;
	}
	/* Container units follow the UI text scale. Too narrow to share the row:
	   the conditions drop to their own row below the tabs, ruled above. */
	@container canvas-panel (max-width: 45em) {
		.right-tabs { flex-wrap: wrap; padding-inline: 10px; }
		.rtab { padding-inline: 12px; }
		.render-meta-strip {
			flex: 1 0 100%;
			margin-left: 0;
			padding: 5px 0 6px;
			border-left: none;
			border-top: 1px solid var(--border);
		}
	}
	/* Narrower still: the heading and the lineage take a line above the items. */
	@container canvas-panel (max-width: 32em) {
		.render-meta-strip { flex-direction: column; align-items: stretch; gap: 2px; }
		.render-meta-context { flex-direction: row; align-items: baseline; flex-wrap: wrap; gap: 10px; }
	}
	.canvas-area {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg2);
		position: relative;
		overflow: hidden;
		/* Sized for the work's action menu below: nothing inside uses container
		   units or an unnamed container query otherwise. */
		container: canvas-area / size;
	}
	/* The menu opens downward from the canvas's top right, which starts lower
	   than the tabs' row it opened from before. It scrolls inside the canvas
	   area rather than being cut off by it: the area's height less the top
	   offset, the trigger and the gap (12 + 34 + 6) and a margin below. */
	.canvas-work-actions :global(.work-action-menu .work-action-dropdown) { max-height: calc(100cqh - 64px); overflow-y: auto; }
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
		font-size: var(--ui-font-size-20);
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
		font-size: var(--ui-font-size-11);
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
	.nav-counter { font-size: var(--ui-font-size-11); color: var(--fg3); font-variant-numeric: tabular-nums; white-space: nowrap; }
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
