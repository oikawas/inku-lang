import { pipelineDescription } from '$lib/description-labels';
import { hasDdlBody } from '$lib/ddl-source';
import { limitNotesToShow } from '$lib/limitNotes';
import { t, getLang } from '$lib/i18n/index.svelte';
import { normalizeSketchState, type SketchState } from '$lib/sketch';
import {
	compositionOption, sketchModeForRoute,
	type CompositionMode, type DrawRoute
} from '$lib/draw-route';
import { composeFallbackReason, composeFallbackState, composeFallbackValue, interpretFallbackReason as interpretReason } from '$lib/composeFallback';
import { needsFallbackRefineConfirm, rememberFallbackRefineConfirm, type FallbackRefineParent } from '$lib/fallbackRefineGate';
import { submitDerivationKind as submitDerivationKindOf, type DerivationKind } from '$lib/derivation';
import { modelDisplayName, qualifiedModelRef, type Provider, type ProviderGroup } from '$lib/models';
import { AUTO_CATALOG_ID, colorCatalogOverride, resolveCatalogId } from '$lib/features/color-catalog/render';
import { renderSettingsPayload } from '$lib/features/render-payload';
import { runCurrentWork, type InstructionLang, type PaintOptions, type PaintResult, type Seed } from '$lib/features/run/current-work';
import { batchSettings } from '$lib/features/batch/settings.svelte';
import { wildOverride } from '$lib/features/wild/render';
import type { NumberedLine } from '$lib/features/batch/resume';
import { getCanvasAspectOption, type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import { canvasRatioLabel, canvasRatioOfAspect, declaredCanvasRatio, sameCanvasRatio, type CanvasRatio } from '$lib/canvas-ratio';
import type { HistoryItem } from '$lib/historyManagerState.svelte';
import type { ReplayComparison } from '$lib/features/history/replay';
import type { JuxtapositionResult } from '$lib/features/juxtaposition/juxtaposition';
import type { AutonomousRun, AutonomousRunsApi } from '$lib/features/autonomous/runs';
import type { SessionState } from '$lib/features/session/state.svelte';
import { BatchState } from '$lib/features/batch/state.svelte';
import { ImageFolderBatch } from '$lib/features/batch/image-folder.svelte';
import { startBatchLease, type BatchLeaseRecord } from '$lib/features/batch/lease';
import { ConnectionFailure, isConnectionFailure } from '$lib/transport/connection-failure';
import { DemoState } from '$lib/features/demo/state.svelte';
import { RefinementSessionState } from '$lib/features/canvas/refinement-session.svelte';
import { HistoryBrowsingState } from '$lib/features/history/browsing-state.svelte';
import { CanvasViewportState } from '$lib/features/canvas/viewport-state.svelte';
import type { SaveHistoryOptions } from '$lib/features/history/save';
import { PipelineApi, PipelineApiError, pipelineDiagnostics, pipelinePatch, pipelineViewFromErrorDetail, type PipelineOptions, type PipelineView, type UploadedPipelineImage } from '$lib/features/pipeline/api';
import { PipelineController } from '$lib/features/pipeline/controller';
import { readExifFacts } from '$lib/features/image-provenance/exif';
import { imageProvenanceText } from '$lib/features/image-provenance/provenance';
import { imageProvenanceSettings } from '$lib/features/image-provenance/settings.svelte';
import { runningStageLabel, type ProviderAttemptCount } from '$lib/paintStream';
import { copyDrawDefaults, copyDrawOptions, type DrawDefaults, type DrawOptions, type DrawTab } from '$lib/features/draw-options';

type Iteration = HistoryItem;
type BatchPaintResult = PaintResult & { ddl: string; thinking: string | null; };

export type WorkStateDeps = {
	apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
	describeApiError: (detail: unknown, status: number) => string;
	session: SessionState;
	batch: BatchState<BatchPaintResult, Iteration>;
	demo: DemoState<BatchPaintResult>;
	refinementSession: RefinementSessionState;
	history: () => HistoryBrowsingState;
	canvasViewport: CanvasViewportState;
	models: {
		stage1Provider: () => Provider;
		stage1Model: () => string;
		stage2Provider: () => Provider;
		stage2Model: () => string;
		visionProvider: () => Provider;
		visionModel: () => string;
		includeThinking: () => boolean;
		available: () => ProviderGroup[];
	};
	canvasAspectId: () => CanvasAspectId;
	resetTargetScopedState: () => void;
	ensureVisibleLineageParentId: () => Promise<string | null>;
	showCanvas: () => void;
	requestConfirmation: (confirmation: { message: string; run: () => void; destructive?: boolean; runLabel?: string; secondaryLabel?: string; secondaryRun?: () => void; hideCancel?: boolean; cancelRun?: () => void; }) => void;
	displayLatestBatchRender: () => void;
	loadBatchSavedWork: (id: string) => Promise<Iteration>;
	pushHistory: (item: Iteration, options?: SaveHistoryOptions) => Promise<Iteration | null>;
	/** The warning that a picture goes to the provider, due before the first picture after a sign-in. */
	imageUploadNotice?: { due: () => boolean; acknowledge: () => void };
};

export function createWorkState(deps: WorkStateDeps) {
	const { apiFetch, batch, demo, refinementSession, canvasViewport } = deps;
	const { describeApiError, session } = deps;
	const effectiveCanvasAspectId = deps.canvasAspectId;
	const resetTargetScopedState = deps.resetTargetScopedState;
	const ensureVisibleLineageParentId = deps.ensureVisibleLineageParentId;
	const displayLatestBatchRender = deps.displayLatestBatchRender;
	const pushHistory = deps.pushHistory;

	// ── Input ───────────────────────────────────────────────
	const DEFAULT_INPUT = '山の向こうに月が昇る';

	let inputMode = $state<'single' | 'image' | 'batch'>('single');
	let imageProvenance = $state('');
	let uploadedImage = $state<UploadedPipelineImage | null>(null);
	let imageFileName = $state('');
	let imageUploading = $state(false);
	const initialOptions = (image: boolean): DrawOptions => ({ route: 'read_and_draw', sketch: 'on', composition: 'off', wild: 'off',
		catalog: { id: 'default', mode: 'fixed' }, canvas_aspect: image ? 'image' : 'square', models: {} });
	let drawDefaults = $state<DrawDefaults>({ describe: initialOptions(false), image: initialOptions(true), batch_text: initialOptions(false), batch_image: initialOptions(true) });
	let drawChoices = $state<DrawDefaults>({ describe: initialOptions(false), image: initialOptions(true), batch_text: initialOptions(false), batch_image: initialOptions(true) });
	let defaultsOwner: string | null = null;
	function activeDrawTab(): DrawTab {
		return inputMode === 'single' ? 'describe' : inputMode === 'image' ? 'image'
			: imageFolder.source === 'image' ? 'batch_image' : 'batch_text';
	}
	function currentOptions(): DrawOptions { return drawChoices[activeDrawTab()]; }
	/** The drawing model of the tab on screen; the legacy setting only before the
	 *  user's defaults have loaded. Derived drawings use this, not the legacy one. */
	function tabModelRef(stage: 'stage1' | 'stage2'): string {
		return currentOptions().models[stage] ?? (stage === 'stage1'
			? qualifiedModelRef(deps.models.stage1Provider(), deps.models.stage1Model())
			: qualifiedModelRef(deps.models.stage2Provider(), deps.models.stage2Model()));
	}
	/** The catalog choice of the tab on screen, as a catalog override reads it. */
	function tabCatalogSelection(options: DrawOptions = currentOptions()): string {
		const catalog = options.catalog;
		return catalog.mode === 'auto' ? AUTO_CATALOG_ID : catalog.id;
	}
	function setDrawDefaults(owner: string, defaults: DrawDefaults): void {
		drawDefaults = copyDrawDefaults(defaults);
		if (defaultsOwner !== owner) {
			drawChoices = copyDrawDefaults(defaults);
			defaultsOwner = owner;
		}
	}
	// Opening a work takes its recorded choices through the shared core's rule
	// (the Server answers). Only the latest opening's answer is applied.
	let adoptSequence = 0;
	let adoptTab: DrawTab | null = null;
	function beginWorkOptions(tab: DrawTab): number { adoptTab = tab; return ++adoptSequence; }
	function invalidateWorkOptions(): void { if (activeDrawTab() === adoptTab) adoptSequence += 1; }
	function adoptWorkOptions(sequence: number, tab: DrawTab, options: DrawOptions): void {
		if (sequence === adoptSequence) drawChoices[tab] = copyDrawOptions(options);
	}
	let imageUploadOrdinal = 0;
	let imageFile: File | null = null;
	let imageUploadConsumed = false;
	let imageRunActive = $state(false);
	// Set when the author types in the source note. A chosen image then leaves
	// the note alone; otherwise it fills it with the file name and Exif.
	let imageProvenanceTyped = false;
	function clearImage(): void {
		if (imageRunActive) {
			submitStopRequested = true;
			submitAbortController?.abort();
			// Clearing shows nothing; only the cancel stops the run behind it.
			pipelineController.clear();
			cancelPipelineRun();
		}
		imageUploadOrdinal += 1;
		imageFile = null;
		uploadedImage = null;
		imageFileName = '';
		imageProvenance = '';
		imageProvenanceTyped = false;
		imageUploading = false;
		imageUploadConsumed = false;
	}

	/** The source note the picture tab writes for a chosen file, from its name and Exif. */
	async function provenanceOfFile(file: File): Promise<string> {
		const options = imageProvenanceSettings.options;
		let facts = null;
		if (options.includeExif) {
			try {
				facts = readExifFacts(await file.arrayBuffer());
			} catch {
				facts = null;
			}
		}
		const strings = t();
		return imageProvenanceText(file.name, facts, options, {
			fileName: strings.imageProvenanceFileName,
			takenAt: strings.imageProvenanceTakenAt,
			camera: strings.imageProvenanceCamera,
			lens: strings.imageProvenanceLens,
			exposure: strings.imageProvenanceExposure,
		});
	}

	async function fillImageProvenance(file: File, ordinal: number): Promise<void> {
		const text = await provenanceOfFile(file);
		// A note the author typed and then emptied is filled again.
		if (ordinal !== imageUploadOrdinal || (imageProvenanceTyped && imageProvenance.trim())) return;
		imageProvenance = text;
	}

	let input = $state(DEFAULT_INPUT);

	const instructionLang: InstructionLang = 'auto';

	let stage1UserPrompt = $state('');

	// ── Loading ─────────────────────────────────────────────
	let loading = $state(false);

	let activeRunMode = $state<'single' | 'batch' | 'image-batch' | 'demo' | null>(null);

	let submitAbortController: AbortController | null = null;

	let submitStopRequested = false;

	let replayAbortController: AbortController | null = null;

	let replayStopRequested = false;

	let stageLabel = $state('');

	let error = $state<string | null>(null);

	// ── Replay ──────────────────────────────────────────────
	let reloading = $state(false);

	let reloadError = $state<string | null>(null);

	let replayComparison = $state<ReplayComparison | null>(null);

	// ── Result ──────────────────────────────────────────────
	let ddl = $state<string | null>(null);

	let ddlGeneratedBaseline = $state<string | null>(null);

	let thinking = $state<string | null>(null);

	let result = $state.raw<PaintResult | null>(null);

	/** The author's choice of route. Read and draw starts with the sketch on
	 *  (the author's answer, 2026-10-25); the current stages leave it alone. */
	function selectDrawRoute(route: DrawRoute): void {
		if (route !== currentOptions().route) invalidateWorkOptions();
		if (route !== currentOptions().route) currentOptions().sketch = sketchModeForRoute(route, currentOptions().sketch);
		currentOptions().route = route;
	}

	function selectCompositionMode(mode: CompositionMode): void {
		if (mode !== currentOptions().composition) invalidateWorkOptions();
		currentOptions().composition = mode;
	}

	// The reading belonging to the work on screen, shown without an editor.
	let sketchText = $state<string | null>(null);

	// Which description the prose was written for. Prose written for one text is
	// not prose for another, and the description can be edited after a run.
	let sketchSource = $state<string | null>(null);

	// What the record says the layer did for the work on screen. `null` is a work
	// whose record is absent -- drawn before the column existed -- and the note
	// tells that apart from 'off', which is a choice the author made.
	let sketchState = $state<SketchState | null>(null);

	/** The prose to send for this description, or null to let the layer write it.
	 *  Used by the paths that re-run one stage over a description already on
	 *  screen (model comparison): holding the prose fixed is what
	 *  makes those a comparison of models rather than of two different texts. */
	function sketchTextFor(text: string): string | null {
		return sketchText && sketchSource !== null && sketchSource.trim() === text.trim()
			? sketchText
			: null;
	}

	/** Show the saved reading without changing the next drawing's choices. */
	function adoptSketch(
		text: string | null,
		grain: unknown,
		source: string | null = null,
		state: unknown = null
	): void {
		sketchText = text;
		sketchSource = source;
		void grain;
		sketchState = normalizeSketchState(state);
	}

	let pendingCanvasAspectDerivation = $state<{ parentNodeId: string; fromAspectId: CanvasAspectId; toAspectId: CanvasAspectId; } | null>(null);

	let lineageDetached = $state(false);

	// ── Timer ───────────────────────────────────────────────
	let elapsedStage1Ms = $state(0);

	let elapsedStage2Ms = $state(0);

	let elapsedTotalMs = $state(0);

	let liveMs = $state(0);

	let _timerStart = 0;

	let _timerHandle: ReturnType<typeof setInterval> | null = null;

	// ── Tokens ──────────────────────────────────────────────
	let tokensInStage1 = $state<number | null>(null);

	let tokensOutStage1 = $state<number | null>(null);

	let tokensInStage2 = $state<number | null>(null);

	let tokensOutStage2 = $state<number | null>(null);

	// ── History ─────────────────────────────────────────────
	let displayedHistoryItem = $state<Iteration | null>(null);

	// The persisted pipeline is the authority for every newly authored single
	// work. A selected history row remains the immutable performance on screen;
	// its id records the exact parent that a subsequent author action must fork.
	let pipelineView = $state<PipelineView | null>(null);
	let pipelineBusy = $state(false);

	function pipelineOptions(options: PaintOptions = {}): PipelineOptions {
		const selected = currentOptions();
		const render = renderSettingsPayload('paint', { ...colorCatalogOverride(tabCatalogSelection()),
			...wildOverride(selected.wild === 'on'), ...options.renderOverrides });
		const route = options.route ?? currentOptions().route;
		return {
			route,
			...compositionOption(route, options.compositionMode ?? currentOptions().composition),
			sketch: options.sketchMode ?? currentOptions().sketch,
			...(options.sketchText ? { sketch_text: options.sketchText } : {}),
			stage1_model: options.stage1Model ?? tabModelRef('stage1'),
			stage2_model: options.stage2Model ?? tabModelRef('stage2'),
			instruction_lang: instructionLang,
			ui_lang: getLang(),
			catalog_id: typeof render.catalog_id === 'string' ? render.catalog_id : resolveCatalogId(tabCatalogSelection()),
			catalog_mode: typeof render.catalog_mode === 'string' ? render.catalog_mode : undefined,
			canvas_aspect: options.canvasAspectId ?? selected.canvas_aspect,
			...(options.canvasFit ? { canvas_fit: options.canvasFit } : {}),
			render_seed: options.renderSeed,
			composition_seed: options.compositionSeed,
			wild: typeof render.wild === 'boolean' ? render.wild : undefined,
			history_display_label: options.displayLabel,
			batch_line_number: options.batchLineNumber,
			batch_run_id: options.batchRunId,
			lineage_parent_node_id: options.lineageParentNodeId ?? undefined,
			derivation_kind: options.derivationKind ?? undefined,
			derivation_metadata: options.derivationMetadata,
			...(options.importedPlugins?.length ? { imported_plugins: options.importedPlugins } : {}),
			count_generation: options.countGeneration ?? true,
		};
	}

	// The run's progress, also while the author looks at another work.
	function followRunProgress(view: PipelineView): void {
		activeRunAttempt = view.provider_attempt ?? null;
		activeRunProgress = view.progress ? { event: 'progress', ...view.progress } : null;
		// A read-and-draw run whose DDL is committed is drawn and saved next.
		if (loading && view.route === 'read_and_draw' && view.delivery?.score && !view.result) stageLabel = t().readDrawSaving;
	}

	function adoptPipelineView(view: PipelineView | null): void {
		pipelineView = view;
		activeRunAttempt = view?.provider_attempt ?? null;
		activeRunProgress = view?.progress ? { event: 'progress', ...view.progress } : null;
		if (!view) return;
		followRunProgress(view);
		if (view.image_ddl || view.image_provenance != null) {
			imageProvenance = view.image_provenance ?? '';
			input = '';
			stage1UserPrompt = '';
		} else {
			input = view.description;
			stage1UserPrompt = view.description;
		}
		if (view.document) {
			ddl = view.document.source;
			ddlGeneratedBaseline = view.document.source;
		}
		if (!view.result) return;
		const painted = view.result;
		result = painted;
		adoptSketch(painted.sketch_text ?? null, painted.sketch_grain, view.description, painted.sketch_state);
		thinking = painted.thinking ?? null;
		elapsedStage1Ms = painted.elapsed_stage1_ms;
		elapsedStage2Ms = painted.elapsed_stage2_ms;
		elapsedTotalMs = painted.elapsed_total_ms;
		tokensInStage1 = painted.tokens_in_stage1;
		tokensOutStage1 = painted.tokens_out_stage1;
		tokensInStage2 = painted.tokens_in_stage2;
		tokensOutStage2 = painted.tokens_out_stage2;
		deps.showCanvas();
		canvasViewport.fit();
	}

	const pipelineController = new PipelineController(
		new PipelineApi(apiFetch),
		() => pipelineOptions(),
		adoptPipelineView,
		undefined,
		followRunProgress,
	);

	async function selectImage(file: File): Promise<void> {
		const ordinal = ++imageUploadOrdinal;
		imageFile = file;
		imageUploadConsumed = false;
		uploadedImage = null;
		imageFileName = file.name;
		imageUploading = true;
		error = null;
		void fillImageProvenance(file, ordinal);
		try {
			const image = await new PipelineApi(apiFetch).uploadImage(file);
			if (ordinal === imageUploadOrdinal) uploadedImage = image;
		} catch (cause) {
			if (ordinal === imageUploadOrdinal) error = cause instanceof PipelineApiError
				? describeApiError(cause.detail, cause.status) : String(cause);
		} finally {
			if (ordinal === imageUploadOrdinal) imageUploading = false;
		}
	}

	async function submitImage(): Promise<void> {
		if (!uploadedImage || imageUploading || loading || reloading || pipelineBusy || refinementSession.gridBusy || demo.running || batch.resuming) return;
		let image = uploadedImage;
		const provenance = imageProvenance;
		const choices = copyDrawOptions(drawChoices.image);
		const model = choices.models.vision ?? qualifiedModelRef(deps.models.visionProvider(), deps.models.visionModel());
		const selectedCatalog = tabCatalogSelection(choices);
		const catalog = renderSettingsPayload('paint', colorCatalogOverride(selectedCatalog));
		const abortController = new AbortController();
		submitAbortController = abortController;
		submitStopRequested = false;
		loading = true;
		imageRunActive = true;
		activeRunMode = 'single';
		error = null;
		ddl = null; ddlGeneratedBaseline = null; thinking = null; result = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		resetTargetScopedState();
		pendingCanvasAspectDerivation = null;
		pipelineController.clear();
		adoptSketch(null, null, null, 'off');
		stageLabel = t().imageWritingDdl;
		startTimer();
		try {
			if (imageUploadConsumed && imageFile) {
				image = await new PipelineApi(apiFetch).uploadImage(imageFile, abortController.signal);
				abortController.signal.throwIfAborted();
				uploadedImage = image;
			}
			imageUploadConsumed = true;
			const imageCanvasAspectId = choices.canvas_aspect;
			const view = await finishPipeline(() => pipelineController.fromImage(image.image_id, provenance, imageCanvasAspectId, {
				...pipelineOptions(), stage1_model: model, stage2_model: model,
				catalog_id: typeof catalog.catalog_id === 'string' ? catalog.catalog_id : 'default', catalog_mode: choices.catalog.mode,
				// A picture has no sketch and keeps the stroke limit, as before the
				// per-tab choices: the image tab shows neither switch.
				sketch: 'off', sketch_text: undefined, wild: false,
				canvas_aspect: imageCanvasAspectId === 'image' ? image.nearest_format_id : imageCanvasAspectId,
				canvas_fit: 'contain',
			}, abortController.signal));
			if (view.image_failure) error = describeApiError(view.image_failure, 422);
			else if (view.phase.tag === 'failed') error = describeApiError({ code: view.phase.reason ?? 'image_ddl_failed' }, 422);
		} catch (cause) {
			if (!submitStopRequested && !abortController.signal.aborted) {
				error = cause instanceof PipelineApiError ? describeApiError(cause.detail, cause.status)
					: cause instanceof Error ? cause.message : String(cause);
			}
		} finally {
			if (submitAbortController === abortController) submitAbortController = null;
			submitStopRequested = false;
			stopTimer(); loading = false; imageRunActive = false; activeRunMode = null; stageLabel = '';
		}
	}

	/** Paints from a picture once the author has gone on past the upload warning, if it is due. */
	function afterImageUploadNotice(run: () => void): void {
		const notice = deps.imageUploadNotice;
		if (!notice?.due()) {
			run();
			return;
		}
		deps.requestConfirmation({
			message: t().imageUploadNoticeMessage,
			runLabel: t().imageUploadNoticeContinue,
			run: () => { notice.acknowledge(); run(); },
		});
	}

	function requestSubmitImage(): void {
		afterImageUploadNotice(confirmSubmitImage);
	}

	function confirmSubmitImage(): void {
		if (ddl !== null && ddlGeneratedBaseline !== null && ddl !== ddlGeneratedBaseline && !loading && !reloading) {
			deps.requestConfirmation({
				message: t().confirmDdlOverwriteMessage,
				runLabel: t().confirmOk,
				hideCancel: false,
				run: () => { void submitImage(); },
				secondaryLabel: t().ddlPaintButton,
				secondaryRun: () => { void replay(); },
			});
			return;
		}
		void submitImage();
	}

	// ── Picture batch ───────────────────────────────────────
	// Each picture of a picked folder goes the picture tab's way: upload, write
	// the instructions from it with the vision model, paint, save. The source note
	// is the one the picture tab would write for that file.
	const imageFolder = new ImageFolderBatch();

	// The batch's pictures run on a controller of their own. On the shared one,
	// opening a saved work while a picture ran moved its request ordinal, and the
	// run returned half-way without an error: the picture was counted painted
	// and never performed or saved (2026-10-25, 3 of 5 saved).
	const followsImageBatch = () => inputMode === 'batch' && imageFolder.source === 'image';
	const imageBatchController = new PipelineController(
		new PipelineApi(apiFetch),
		() => pipelineOptions(),
		// The canvas follows the batch only while the author is on its tab.
		(view) => { if (followsImageBatch()) adoptPipelineView(view); },
		undefined,
		(view) => { if (followsImageBatch()) followRunProgress(view); },
	);

	async function paintPictureFile(file: File, signal: AbortSignal, choices: DrawOptions, runId?: string, lease?: string): Promise<void> {
		const imageCanvasAspectId = choices.canvas_aspect;
		const selectedCatalog = tabCatalogSelection(choices);
		const catalog = renderSettingsPayload('paint', colorCatalogOverride(selectedCatalog));
		const api = new PipelineApi(apiFetch);
		const provenance = await provenanceOfFile(file);
		const image = await api.uploadImage(file, signal);
		signal.throwIfAborted();
		const model = choices.models.vision ?? qualifiedModelRef(deps.models.visionProvider(), deps.models.visionModel());
		stageLabel = t().imageWritingDdl;
		let view: PipelineView;
		try {
			view = await imageBatchController.fromImage(image.image_id, provenance, imageCanvasAspectId, {
				...pipelineOptions(), stage1_model: model, stage2_model: model,
				catalog_id: typeof catalog.catalog_id === 'string' ? catalog.catalog_id : 'default', catalog_mode: choices.catalog.mode,
				sketch: 'off', sketch_text: undefined, wild: false,
				batch_run_id: runId, batch_line_number: runId ? imageFolder.current : undefined, batch_lease: lease,
				canvas_aspect: imageCanvasAspectId === 'image' ? image.nearest_format_id : imageCanvasAspectId,
				canvas_fit: 'contain',
			}, signal);
		} finally {
			activeRunAttempt = null;
			activeRunProgress = null;
		}
		if (view.image_failure) throw new Error(describeApiError(view.image_failure, 422));
		if (view.phase.tag === 'failed') throw new Error(describeApiError({ code: view.phase.reason ?? 'image_ddl_failed' }, 422));
		// Only a saved work counts as painted; anything short of that is a failure
		// the next Continue paints again, never a silent success.
		const historyId = view.result?.history_id;
		if (!historyId) throw new Error(t().imageFolderNotSaved(view.phase.tag));
		if (followsImageBatch()) {
			await deps.history().fetchOffset(0, { anchorId: historyId });
			displayedHistoryItem = deps.history().items.find((item) => item.id === historyId) ?? null;
		} else {
			await deps.history().refreshAfterServerSave();
		}
	}

	/** A cut or a Server that is away stops the run; it resumes from the same picture. */
	function pictureRunLost(cause: unknown): boolean {
		return isConnectionFailure(cause) || cause instanceof TypeError
			|| (cause instanceof PipelineApiError && [502, 503, 504].includes(cause.status));
	}

	function runImageFolder(fromStart: boolean): void {
		afterImageUploadNotice(() => { void paintImageFolder(fromStart); });
	}

	async function refreshImageBatchResume(reconcile = false, forStart = false, shared?: Promise<Response>): Promise<boolean> {
		const record = forStart ? imageFolder.rawRecord : imageFolder.record;
		if (!record?.batchRunId) { imageFolder.resumeBlocked = false; return true; }
		imageFolder.resumeBlocked = true;
		try {
			const response = shared ? (await shared).clone() : await apiFetch('/api/pipeline/batches', { cache: 'no-store' });
			if (!response.ok) return false;
			const data = await response.json() as { batches?: BatchLeaseRecord[] };
			const found = data.batches?.find((item) => item.run_id === record.batchRunId);
			if (imageFolder.rawRecord?.batchRunId !== record.batchRunId) return false;
			if (!found || found.state === 'running' || found.state === 'uncertain') return false;
			if (!record.batchKeys || record.batchKeys.length !== found.total) return false;
			if (reconcile && imageFolder.record) {
				const saved = (found.conditions as unknown as { draw_options?: DrawOptions } | undefined)?.draw_options;
				if (saved) drawChoices.batch_image = copyDrawOptions(saved);
				const lines: number[] = [];
				for (let offset = 0; ; offset += 100) {
					const params = new URLSearchParams({ offset: String(offset), limit: '100', include_svg: 'false', batch_run_id: record.batchRunId });
					const page = await apiFetch(`/api/history?${params}`, { cache: 'no-store' });
					if (!page.ok) return false;
					const values = await page.json() as { items?: Array<{ batch_run_id?: string; batch_line_number?: number }> };
					if (!Array.isArray(values.items)) return false;
					for (const item of values.items) if (item.batch_run_id === record.batchRunId && typeof item.batch_line_number === 'number') lines.push(item.batch_line_number);
					if (values.items.length < 100) break;
				}
				if (imageFolder.record?.batchRunId !== record.batchRunId) return false;
				imageFolder.markServerCompleted(lines);
			}
			imageFolder.resumeBlocked = false;
			return true;
		} catch { return false; }
	}

	async function paintImageFolder(fromStart: boolean): Promise<void> {
		if (imageFolder.running || loading || reloading || pipelineBusy || refinementSession.gridBusy || demo.running || batch.running || batch.resuming) return;
		loading = true;
		activeRunMode = 'image-batch';
		error = null;
		result = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		resetTargetScopedState();
		pendingCanvasAspectDerivation = null;
		pipelineController.clear();
		adoptSketch(null, null, null, 'off');
		startTimer();
		let lease: Awaited<ReturnType<typeof startBatchLease>> = null;
		const runId = typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function'
			? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`;
		try {
			if (!(await refreshImageBatchResume(!fromStart, true))) throw new Error('The previous image batch may still be running.');
			const choices = copyDrawOptions(drawChoices.batch_image);
			const total = fromStart ? imageFolder.pictures.length : imageFolder.pending.length;
			if (total === 0) return;
			lease = await startBatchLease(apiFetch, runId, '', { draw_options: choices }, total, () => imageFolder.success,
				() => { imageFolder.stop(); void imageBatchController.cancel(); }, 'image');
			await imageFolder.run({
				fromStart,
				batchRunId: lease ? runId : undefined,
				paintPicture: async (file, signal) => {
					if (lease) {
						try { await lease.refresh(); }
						catch (cause) { throw new ConnectionFailure('unreachable', String(cause), { cause }); }
					}
					await paintPictureFile(file, signal, choices, lease ? runId : undefined, lease?.lease);
				},
				stopsTheRun: pictureRunLost,
				describe: (cause) => cause instanceof PipelineApiError ? describeApiError(cause.detail, cause.status)
					: cause instanceof Error ? cause.message : String(cause),
			});
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
		} finally {
			if (lease) await lease.finish(imageFolder.interrupted ? (imageFolder.stopReason ? 'interrupted' : 'stopped') : imageFolder.success === imageFolder.total ? 'completed' : 'interrupted').catch(() => undefined);
			stopTimer(); loading = false; activeRunMode = null; stageLabel = ''; activeRunProgress = null;
		}
	}

	async function pipelineCompatibilityError(response: Response): Promise<Error> {
		const payload = await response.json().catch(() => ({})) as { detail?: unknown };
		const current = pipelineViewFromErrorDetail(payload.detail);
		if (current) pipelineController.adopt(current);
		return new Error(describeApiError(payload.detail, response.status));
	}

	async function finishPipeline(run: () => Promise<PipelineView>): Promise<PipelineView> {
		pipelineBusy = true;
		error = null;
		reloadError = null;
		try {
			const view = await run();
			if (view.result?.history_id && !pipelineController.lastRunWasShown) {
				// The author opened another work meanwhile: the new work joins the
				// history, and the work they look at stays, as for a picture batch.
				await deps.history().refreshAfterServerSave();
			} else if (view.result?.history_id) {
				await deps.history().fetchOffset(0, { anchorId: view.result.history_id });
				displayedHistoryItem = deps.history().items.find((item) => item.id === view.result?.history_id) ?? null;
			}
			return view;
		} catch (cause) {
			if (cause instanceof PipelineApiError && cause.detail.current_view) {
				pipelineController.adopt(cause.detail.current_view);
				throw new Error(describeApiError(cause.detail, cause.status));
			}
			throw cause;
		} finally {
			pipelineBusy = false;
			activeRunAttempt = null;
			activeRunProgress = null;
		}
	}

	function selectHistoryAuthority(historyId: string, variationId?: string | null, signal?: AbortSignal): Promise<boolean> {
		return pipelineController.selectHistory(historyId, variationId, signal);
	}

	function beginNewAuthoring(): void {
		pipelineController.clear();
	}

	async function authorDescription(text: string, options: PaintOptions = {}, signal?: AbortSignal): Promise<PipelineView> {
		// An edited sketch for this very description is drawn as it stands.
		const mode = options.sketchMode ?? currentOptions().sketch;
		const edited = options.sketchText ?? (mode === 'off' ? null : sketchTextFor(text));
		return finishPipeline(() => pipelineController.fromDescription(text, pipelineOptions({ ...options, ...(edited ? { sketchText: edited } : {}) }), signal));
	}

	async function authorDdl(source: string, options: PaintOptions = {}, signal?: AbortSignal): Promise<PipelineView> {
		return finishPipeline(() => pipelineController.fromDdl(source, pipelineOptions(options), signal));
	}

	// A new variation from the description of a work its DDL holds. The work
	// itself is not touched; its description, as it stands, starts again.
	async function forkPipelineDescription(): Promise<void> {
		if (pipelineBusy || !descriptionLocked) return;
		await submit({ fork: true });
	}

	async function approvePipelinePatch(): Promise<void> {
		if (pipelineBusy) return;
		await finishPipeline(() => pipelineController.approvePatch());
	}

	async function declinePipelinePatch(): Promise<void> {
		if (pipelineBusy) return;
		await finishPipeline(() => pipelineController.declinePatch());
	}

	// Which works this screen has already asked about. Kept here and not on the
	// server: the question is about this sitting, not about the work (contract
	// §5-7). See $lib/fallbackRefineGate.
	const fallbackRefineAsked = new Set<string>();
	// The work on screen is held by its DDL: the saved work the server marked
	// (an edit, or derived from one without reading the description again), or,
	// before it is saved, the authoring variation. A DDL drawn again unedited is
	// a DDL-authoritative variation, yet held only if its parent was, so once
	// the variation's work is saved, the server's mark decides.
	const descriptionLocked = $derived.by(() => {
		const saved = displayedHistoryItem?.description_locked;
		if (!pipelineView) return saved === true;
		if (saved !== undefined && displayedHistoryItem?.id === pipelineView.result?.history_id) return saved;
		return pipelineView.authority.authority === 'ddl_authoritative';
	});
	const ddlEditedAfterGeneration = $derived(inputMode === 'single' && ddl !== null && ddlGeneratedBaseline !== null && ddl !== ddlGeneratedBaseline);
	const canSubmit = $derived(
		inputMode === 'single' ? !!pipelineDescription(input).trim() : inputMode === 'batch' ? batch.nonEmpty > 0 : false
	);
	const interpretFallbackReason = $derived(interpretReason(displayedHistoryItem, result));
	const composeFallbackRaw = $derived(
		displayedHistoryItem
			? (displayedHistoryItem.compose_fallback ?? null)
			: (result ? composeFallbackValue(result) : null)
	);

	/** The work a refinement started from the canvas would descend from.
	 *  Built from the same two derivations the badges read, so the dialog and
	 *  the mark can never disagree about whether the words were lost. */
	function currentRefineParent(): FallbackRefineParent {
		return {
			id: displayedHistoryItem?.id ?? result?.history_id ?? null,
			interpret_fallback: interpretFallbackReason,
			compose_fallback: composeFallbackRaw
		};
	}

	/** Whether the next drawing from the input panel would hang under a parent.
	 *  Detached, or with nothing on the canvas, it is a new work rather than a
	 *  refinement, and nothing is being carried forward to ask about. Mirrors
	 *  the parent expression submit() and replay() compute for themselves. */
	function submitWouldRefine(): boolean {
		const parentNodeId = pendingCanvasAspectDerivation?.parentNodeId
			?? (lineageDetached ? null : (displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null));
		return parentNodeId !== null;
	}

	/** Ask before refining from a work drawn by a fallback, and wait for the
	 *  answer. Resolves true when the refinement may go ahead -- which is
	 *  immediately, and without a dialog, for every unmarked work. */
	function confirmFallbackRefine(parent: FallbackRefineParent): Promise<boolean> {
		if (!needsFallbackRefineConfirm(parent, fallbackRefineAsked)) return Promise.resolve(true);
		return new Promise((resolve) => {
			deps.requestConfirmation({
				message: t().confirmRefineFromFallbackMessage,
				runLabel: t().confirmRefineFromFallbackContinue,
				run: () => { rememberFallbackRefineConfirm(parent, fallbackRefineAsked); resolve(true); },
				cancelRun: () => resolve(false)
			});
		});
	}

	// ── Running-indicator state ─────────────────────────────
	// Tokens confirmed by the stage1 event of the paint currently in flight.
	// Cleared when that paint finishes; completed runs are folded into the
	// per-flow totals below.
	let activeRunTokensIn = $state<number | null>(null);

	let activeRunTokensOut = $state<number | null>(null);

	// The model call that paint waits on, as its pipeline view or its stream
	// reports it; null between calls and once the paint finishes.
	let activeRunAttempt = $state<ProviderAttemptCount | null>(null);
	let activeRunProgress = $state<import('../../paintStream.ts').PaintProgressEvent | null>(null);

	// Flows that issue several paints per run keep their own running totals.
	function addTokens(total: number | null, delta: number | null | undefined): number | null {
		if (delta === null || delta === undefined) return total;
		return (total ?? 0) + delta;
	}

	function paintTokensIn(r: PaintResult): number | null {
		return addTokens(r.tokens_in_stage1 ?? null, r.tokens_in_stage2);
	}

	function paintTokensOut(r: PaintResult): number | null {
		return addTokens(r.tokens_out_stage1 ?? null, r.tokens_out_stage2);
	}

	// ── Timer ───────────────────────────────────────────────
	function startTimer() {
		_timerStart = Date.now();
		liveMs = 0;
		_timerHandle = setInterval(() => {
			const now = Date.now();
			liveMs = now - _timerStart;
			demo.updateLiveTime(now);
		}, 100);
	}

	function stopTimer() {
		if (_timerHandle !== null) { clearInterval(_timerHandle); _timerHandle = null; }
	}

	async function autonomousRequest<T>(path: string, init: RequestInit = {}): Promise<T> {
		const r = await apiFetch(path, init);
		if (!r.ok) {
			const data = await r.json().catch(() => ({})) as { detail?: unknown; };
			throw new Error(describeApiError(data.detail, r.status));
		}
		return await r.json() as T;
	}

	/** The AI refinement's runs, which the Server takes (2026-10-21). The juxtaposition
	 *  asks in the page's language, as the juxtaposition dialog does. */
	const autonomousRuns: AutonomousRunsApi = {
		start: (request) => autonomousRequest<AutonomousRun>('/api/refine/autonomous', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ ...request, language: getLang() })
		}),
		read: (runId, signal) => autonomousRequest<AutonomousRun>(`/api/refine/autonomous/${encodeURIComponent(runId)}`, { signal }),
		stop: (runId) => autonomousRequest<AutonomousRun>(`/api/refine/autonomous/${encodeURIComponent(runId)}/stop`, { method: 'POST' }),
		forHistory: async (historyId, signal) => (await autonomousRequest<{ runs: AutonomousRun[] }>(
			`/api/refine/autonomous?history_id=${encodeURIComponent(historyId)}`, { signal }
		)).runs
	};

	/** Four sentences from the author's other works that a model would add after this work's description. */
	async function requestJuxtaposition(historyId: string, model: string, exclude: string[], signal: AbortSignal): Promise<JuxtapositionResult> {
		const r = await apiFetch('/api/refine/juxtaposition', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ history_id: historyId, model, exclude, language: getLang() })
		});
		if (!r.ok) {
			const data = await r.json().catch(() => ({})) as { detail?: unknown; };
			throw new Error(describeApiError(data.detail, r.status));
		}
		return await r.json() as JuxtapositionResult;
	}

	async function paintOne(text: string, options: PaintOptions = {}): Promise<{ ddl: string; thinking: string | null; } & PaintResult> {
		// This compatibility request starts its own execution. Its result must not
		// be accompanied by a stopped view belonging to an earlier drawing.
		if (!options.batchRunId && !options.detached) pipelineController.clear();
		return runCurrentWork(
			text,
			options,
			{
				uiLang: getLang(),
				strings: t(),
				// Resolve injected route settings before entering the stateless run
				// operation. A caller's one-run override still wins there.
				stage1Model: tabModelRef('stage1'),
				stage2Model: tabModelRef('stage2'),
				includeThinking: deps.models.includeThinking(),
				instructionLang,
				canvasAspectId: currentOptions().canvas_aspect,
				sketchMode: currentOptions().sketch,
				route: currentOptions().route,
				compositionMode: currentOptions().composition,
				renderPayload: renderSettingsPayload('paint', { ...colorCatalogOverride(tabCatalogSelection()),
					...wildOverride(currentOptions().wild === 'on'), ...options.renderOverrides })
			},
			{
				apiFetch,
				describeApiError,
				setStage1UserPrompt: (prompt) => { stage1UserPrompt = prompt; },
				setStageLabel: (label) => { stageLabel = label; },
				setActiveRunTokens: (tokensIn, tokensOut) => {
					activeRunTokensIn = tokensIn;
					activeRunTokensOut = tokensOut;
				},
				attachSavedLineage: () => { lineageDetached = false; },
				updateGenerationCount: (count) => session.updateGenerationCount(count),
				adoptPipelineView: options.batchRunId || options.detached ? undefined : (view) => pipelineController.adopt(view),
				setProviderAttempt: (attempt) => { activeRunAttempt = attempt; },
				setProgress: options.onProgress ?? ((progress) => { activeRunProgress = progress; })
			}
		);
	}

	async function startDemo() {
		if (loading || reloading || batch.resuming || refinementSession.gridBusy) return;
		resetWorkOutput();
		demo.clearInput();
		error = null;
		displayedHistoryItem = null;
		activeRunMode = 'demo';
		loading = true;
		startTimer();
		await demo.start({
			canvasAspectId: effectiveCanvasAspectId,
			// Demo follows the catalog modal, including "from the description";
			// it has no separate catalog or wild-mode setting of its own.
			renderOverrides: () => ({
				...colorCatalogOverride(tabCatalogSelection()),
				...wildOverride(false),
			}),
			paintInstruction: (prompt, paintOptions) => {
				const model = qualifiedModelRef(deps.models.stage1Provider(), deps.models.stage1Model());
				return paintOne(prompt, { ...paintOptions, detached: true, stage1Model: model, stage2Model: model });
			},
			onLatestResult: (painted) => {
				ddl = painted.ddl;
				ddlGeneratedBaseline = painted.ddl;
				thinking = painted.thinking;
				result = painted;
				deps.showCanvas();
				canvasViewport.fit();
				elapsedStage1Ms = painted.elapsed_stage1_ms;
				elapsedStage2Ms = painted.elapsed_stage2_ms;
				elapsedTotalMs = painted.elapsed_total_ms;
				tokensInStage1 = painted.tokens_in_stage1;
				tokensOutStage1 = painted.tokens_out_stage1;
				tokensInStage2 = painted.tokens_in_stage2;
				tokensOutStage2 = painted.tokens_out_stage2;
			},
			onRunFinished: () => {
				stopTimer();
				loading = false;
				activeRunMode = null;
				stageLabel = '';
			},
			refreshAfterServerSave: () => deps.history().refreshAfterServerSave(),
			refreshAfterRun: () => deps.history().refreshAfterRun(),
		});
	}

	function stopDemo() {
		demo.stop();
		loading = false;
		activeRunMode = null;
		stageLabel = '';
		stopTimer();
	}

	// ── Submit ──────────────────────────────────────────────
	function requestSubmit() {
		if (inputMode === 'single' && ddlEditedAfterGeneration && !loading && !reloading) {
			deps.requestConfirmation({
				message: t().confirmDdlOverwriteMessage,
				runLabel: t().confirmOk,
				hideCancel: false,
				run: () => { void submit(); },
				secondaryLabel: t().ddlPaintButton,
				secondaryRun: () => { void replay(); },
			});
			return;
		}
		void submit();
	}

	/**
	 * `resumeLines` finishes a batch that stopped part-way: the lines it names are
	 * painted in place of the whole box, each keeping the number the prompt gave
	 * it. Everything else about the run is unchanged.
	 */
	async function submit(options: { resumeLines?: NumberedLine[]; retryFailedLines?: NumberedLine[]; fork?: boolean; } = {}) {
		if (options.retryFailedLines && inputMode !== 'batch') return;
		if (!canSubmit || loading || refinementSession.gridBusy || (batch.resuming && !options.resumeLines && !options.retryFailedLines)) return;
		// Drawing a held work from its description happens only as the explicit fork.
		if (inputMode === 'single' && descriptionLocked && !options.fork) return;
		// Ask before resetTargetScopedState and before any intermediate save.
		if (submitWouldRefine() && !(await confirmFallbackRefine(currentRefineParent()))) return;
		resetTargetScopedState();
		try {
			await ensureVisibleLineageParentId();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
			return;
		}

		// The lineage lookup may yield to a different drawing action.
		if (options.retryFailedLines && inputMode !== 'batch') return;
		if (loading || reloading || refinementSession.gridBusy || (batch.resuming && !options.resumeLines && !options.retryFailedLines)) return;
		if (inputMode === 'batch') {
			await submitBatch(options);
			return;
		}
		if (inputMode !== 'single') return;

		const abortController = new AbortController();
		submitAbortController = abortController;
		submitStopRequested = false;
		const canvasAspectDerivation = pendingCanvasAspectDerivation;
		const submitParentNodeId = canvasAspectDerivation?.parentNodeId ?? (lineageDetached ? null : (displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null));
		const submitSource = displayedHistoryItem?.source_text ?? displayedHistoryItem?.input ?? input;
		const submitTextChanged = input.trim() !== submitSource.trim();
		// Sketching (Stage 0.5). The grain edge fires only when the grain differs from
		// the parent's, exactly as description_edit fires only when the text does;
		// one edge, one cause, so a changed description stays a description edit.
		const submitDerivationKind: DerivationKind | null = options.fork && submitParentNodeId !== null ? 'description_edit' : submitDerivationKindOf({
			hasParent: submitParentNodeId !== null,
			canvasAspectChanged: canvasAspectDerivation !== null,
			textChanged: submitTextChanged,
			grainChanged: false,
		});
		const submitDerivationMetadata = canvasAspectDerivation
			? { from_canvas_aspect: canvasAspectDerivation.fromAspectId, to_canvas_aspect: canvasAspectDerivation.toAspectId }
			: {};

		loading = true; error = null;
		activeRunMode = 'single';
		ddl = null; ddlGeneratedBaseline = null; thinking = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		startTimer();

		try {
			stageLabel = currentOptions().route === 'read_and_draw'
				? (currentOptions().sketch === 'off' ? t().readDrawWriting : t().readDrawReading)
				: t().stageDdlGenerating;
			const view = await authorDescription(input, {
				sourceText: input,
				canvasAspectId: effectiveCanvasAspectId(),
				lineageParentNodeId: submitParentNodeId,
				derivationKind: submitDerivationKind,
				derivationMetadata: submitDerivationMetadata,
			}, abortController.signal);
			if (submitStopRequested) return;
			if (view.result?.history_id && submitAbortController === abortController && !submitStopRequested
				&& pipelineController.lastRunWasShown) {
				if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
				lineageDetached = false;
			}
		} catch (cause) {
			if (!(submitStopRequested || abortController.signal.aborted)) {
				error = cause instanceof Error ? cause.message : String(cause);
				// The work the author opened meanwhile keeps its picture.
				if (pipelineController.lastRunWasShown) result = null;
			}
		} finally {
			if (submitAbortController === abortController) submitAbortController = null;
			submitStopRequested = false;
			stopTimer(); loading = false; reloading = false; activeRunMode = null; stageLabel = '';
		}
	}

	async function submitBatch(options: { resumeLines?: NumberedLine[]; retryFailedLines?: NumberedLine[]; }): Promise<void> {
		let savedWork: Iteration | null = null;
		const batchCanvasAspectId = drawChoices.batch_text.canvas_aspect;
		const batchCatalogId = tabCatalogSelection(drawChoices.batch_text);
		const batchStage1Model = drawChoices.batch_text.models.stage1 ?? qualifiedModelRef(deps.models.stage1Provider(), deps.models.stage1Model());
		const batchStage2Model = drawChoices.batch_text.models.stage2 ?? qualifiedModelRef(deps.models.stage2Provider(), deps.models.stage2Model());
		const batchSketchMode = drawChoices.batch_text.sketch;
		const batchRoute = drawChoices.batch_text.route;
		const batchComposition = drawChoices.batch_text.composition;
		const batchWild = drawChoices.batch_text.wild === 'on';
		// The batch owns its line failures; the previous single-work run is no longer current.
		pipelineController.clear();
		loading = true; error = null;
		activeRunMode = 'batch';
		ddl = null; ddlGeneratedBaseline = null; thinking = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		deps.showCanvas();
		startTimer();

		try {
			await batch.run({
				resumeLines: options.resumeLines,
				retryFailedLines: options.retryFailedLines,
				runConditions: {
					stage1Model: batchStage1Model,
					stage2Model: batchStage2Model,
					catalogId: batchCatalogId,
					catalogMode: batchCatalogId === AUTO_CATALOG_ID ? 'auto' : 'fixed',
					sketchGrain: batchSketchMode === 'off' ? null : batchSketchMode,
					wild: batchWild,
					canvasAspectId: batchCanvasAspectId,
					route: batchRoute,
					composition: batchRoute === 'read_and_draw' ? batchComposition : null,
				},
				canvasAspectId: batchCanvasAspectId,
				renderOverrides: { ...colorCatalogOverride(batchCatalogId), ...wildOverride(batchWild) },
				maxRetries: batchSettings.maxRetries,
				paintLine: (text, paintOptions) => paintOne(text, {
					...paintOptions, stage1Model: batchStage1Model, stage2Model: batchStage2Model,
					sketchMode: batchSketchMode, route: batchRoute, compositionMode: batchComposition,
				}),
				onLatestResult: (painted) => {
					thinking = painted.thinking;
					if (inputMode === 'batch' && batch.autoFollowLatest) {
						displayedHistoryItem = savedWork;
						displayLatestBatchRender();
					}
				},
				onPaintComplete: () => { elapsedTotalMs = Date.now() - _timerStart; },
				refreshAfterServerSave: async () => {
					await deps.history().refreshAfterServerSave();
					const id = batch.latestResult?.history_id;
					savedWork = id && inputMode === 'batch' && batch.autoFollowLatest
						? await deps.loadBatchSavedWork(id) : null;
				},
				refreshAfterRun: () => deps.history().refreshAfterRun(),
			});
		} catch (cause) {
			if (!batch.interrupted) {
				error = cause instanceof Error ? cause.message : String(cause);
				result = null;
			}
		} finally {
			stopTimer(); loading = false; reloading = false; activeRunMode = null; stageLabel = '';
		}
	}

	function stopBatch() {
		if (activeRunMode === 'image-batch') {
			imageFolder.stop();
			void imageBatchController.cancel();
			return;
		}
		if (activeRunMode === 'batch') {
			batch.stop();
			return;
		}
		if (activeRunMode !== 'single') return;
		submitStopRequested = true;
		submitAbortController?.abort();
		void pipelineController.cancel();
	}

	function stopReplay() {
		if (!reloading) return;
		replayStopRequested = true;
		replayAbortController?.abort();
		void pipelineController.cancel();
	}

	function stopDdlRender() {
		if (replayAbortController) {
			stopReplay();
			return;
		}
		stopBatch();
	}

	/**
	 * End the pipeline run in flight: the server execution and this tab's
	 * polling of it. An aborted signal alone reaches only the request that
	 * started the run, so a caller that owns its own stop button (the DDL
	 * dialog) needs this as well, as stopBatch and stopReplay already do.
	 */
	function cancelPipelineRun(): void {
		pipelineController.cancel().catch((cause) => {
			console.warn('failed to cancel the pipeline run', cause);
		});
	}

	// ── Replay (Stage 2 only) ───────────────────────────────
	let replayStarting = false;
	function imageBeforeReviewDdl(): string | null {
		if (inputMode !== 'image' || result === null) return null;
		const record = displayedHistoryItem ? displayedHistoryItem.image_ddl
			: result.image_ddl ?? (pipelineView?.result === result ? pipelineView.image_ddl : null);
		const source = record?.before_review;
		return typeof source === 'string' && source.trim() ? source : null;
	}

	async function replayImageBeforeReview(): Promise<void> {
		const source = imageBeforeReviewDdl(), targetResult = result, targetHistory = displayedHistoryItem, targetDdl = ddl;
		if (source === null) return;
		const draw = async () => {
			if (result !== targetResult || displayedHistoryItem !== targetHistory || ddl !== targetDdl || imageBeforeReviewDdl() !== source
				|| loading || reloading || replayStarting || pipelineBusy || refinementSession.gridBusy || demo.running || batch.resuming) return;
			ddl = source;
			await replay({ ddlEdit: true });
		};
		if (ddl !== null && ddlGeneratedBaseline !== null && ddl !== ddlGeneratedBaseline) {
			deps.requestConfirmation({ message: t().confirmDdlOverwriteMessage, runLabel: t().imageBeforeReviewPaint,
				run: () => { void draw(); } });
			return;
		}
		await draw();
	}

	async function replay(options: { ddlEdit?: boolean } = {}) {
		// Reserve the action before the parent/fallback awaits can yield.
		if (replayStarting) return;
		replayStarting = true;
		try { await replayOnce(options); }
		finally { replayStarting = false; }
	}
	async function replayOnce(options: { ddlEdit?: boolean }) {
		if (!ddl || !hasDdlBody(ddl) || reloading) return;
		if (submitWouldRefine() && !(await confirmFallbackRefine(currentRefineParent()))) return;
		resetTargetScopedState();
		try {
			await ensureVisibleLineageParentId();
		} catch (cause) {
			reloadError = cause instanceof Error ? cause.message : String(cause);
			return;
		}
		const canvasAspectDerivation = pendingCanvasAspectDerivation;
		const replayParentNodeId = options.ddlEdit
			? (displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null)
			: canvasAspectDerivation?.parentNodeId ?? (lineageDetached ? null : (displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null));
		// A DDL written for another ratio than this paper: its own declaration,
		// or, for an unedited saved work without one, the paper it was drawn on.
		// A work that records neither is drawn to the paper as before (DDL 26).
		const paperId = effectiveCanvasAspectId();
		const unedited = !options.ddlEdit && replayParentNodeId !== null && ddlGeneratedBaseline !== null && ddl === ddlGeneratedBaseline;
		const parentWorkId = displayedHistoryItem?.id ?? result?.history_id ?? null;
		const recordedWild = displayedHistoryItem?.render_wild ?? result?.render_wild ?? false;
		const parentAspectId = canvasAspectDerivation?.fromAspectId
			?? displayedHistoryItem?.render_canvas_aspect_id ?? result?.render_canvas_aspect_id ?? null;
		const declared = declaredCanvasRatio(ddl);
		const fitBasis = declared ?? (unedited && parentAspectId ? canvasRatioOfAspect(parentAspectId) : null);
		const imageOrigin = !!(displayedHistoryItem?.image_ddl ?? result?.image_ddl ?? pipelineView?.image_ddl);
		const fitChoice = imageOrigin ? 'fit' : await chooseCanvasFit(fitBasis, paperId);
		if (fitChoice === null) return;
		if (fitChoice === 'fit' && unedited && replayParentNodeId && parentWorkId) {
			const abortController = new AbortController();
			replayAbortController = abortController;
			reloading = true; reloadError = null;
			try {
				await drawFittedSavedWork(replayParentNodeId, parentWorkId, paperId, abortController.signal);
				if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
				lineageDetached = false;
			} catch (e) {
				if (!abortController.signal.aborted) reloadError = e instanceof Error ? e.message : String(e);
			} finally {
				if (replayAbortController === abortController) replayAbortController = null;
				reloading = false;
			}
			return;
		}
		const replayKind: DerivationKind | null = options.ddlEdit && replayParentNodeId ? 'ddl_edit' : canvasAspectDerivation
			? 'canvas_aspect_change'
			: replayParentNodeId ? (ddlGeneratedBaseline !== null && ddl !== ddlGeneratedBaseline ? 'ddl_edit' : 'replay') : null;
		const replayDerivationMetadata = canvasAspectDerivation
			? { from_canvas_aspect: canvasAspectDerivation.fromAspectId, to_canvas_aspect: canvasAspectDerivation.toAspectId }
			: {};
		const abortController = new AbortController();
		replayAbortController = abortController;
		replayStopRequested = false;
		reloading = true; reloadError = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		const replayInput = input;
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		stageLabel = t().stageStructuring('');
		startTimer();
		try {
			const view = await authorDdl(ddl, {
				sourceText: replayInput,
				canvasAspectId: paperId,
				...(fitChoice === 'fit' ? { canvasFit: 'contain' as const } : {}),
				lineageParentNodeId: replayParentNodeId,
				derivationKind: replayKind,
				derivationMetadata: replayDerivationMetadata,
				renderOverrides: wildOverride(unedited ? recordedWild : currentOptions().wild === 'on'),
			}, abortController.signal);
			if (view.result) {
				if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
				lineageDetached = false;
			}
		} catch (e) {
			if (!replayStopRequested && !abortController.signal.aborted) {
				reloadError = e instanceof Error ? e.message : String(e);
			}
		} finally {
			if (replayAbortController === abortController) replayAbortController = null;
			replayStopRequested = false;
			stopTimer();
			stageLabel = '';
			reloading = false;
		}
	}

	/** How a DDL written for another ratio is drawn on this paper (DDL 26):
	 *  fitted into it, drawn to it as before, or not drawn (null). A DDL with
	 *  no ratio to go by, or with the paper's, is drawn without asking. */
	function chooseCanvasFit(basis: CanvasRatio | null, paperId: CanvasAspectId): Promise<'fit' | 'stretch' | null> {
		const paper = canvasRatioOfAspect(paperId);
		if (!basis || !paper || sameCanvasRatio(basis, paper)) return Promise.resolve('stretch');
		const option = getCanvasAspectOption(paperId);
		return new Promise((resolve) => {
			deps.requestConfirmation({
				message: t().canvasFitMessage(canvasRatioLabel(basis), `${option.label} ${option.ratio}`),
				runLabel: t().canvasFitRun,
				run: () => resolve('fit'),
				secondaryLabel: t().canvasFitStretch,
				secondaryRun: () => resolve('stretch'),
				cancelRun: () => resolve(null),
			});
		});
	}

	/** The saved work fitted into this paper from its saved Score (はめ込み,
	 *  2026-10-23): the Server draws it, and it is saved as the work's child.
	 *  The DDL stays as it is. */
	async function drawFittedSavedWork(parentNodeId: string, workId: string, paperId: CanvasAspectId, signal: AbortSignal): Promise<void> {
		const response = await apiFetch('/api/render-canvas-fit', {
			method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ work_id: workId, canvas_aspect: paperId }),
		});
		if (!response.ok) {
			const data = await response.json().catch(() => ({})) as { detail?: unknown };
			throw new Error(describeApiError(data.detail, response.status));
		}
		const data = await response.json() as Partial<PaintResult> & Pick<PaintResult, 'svg' | 'score'> & { derivation_metadata?: Record<string, unknown> };
		const derivationMetadata = data.derivation_metadata ?? { to_canvas_aspect: paperId };
		const fitted = {
			...(result ?? {}), ...data,
			history_id: null, history_at: null, lineage_node_id: null,
			lineage_parent_node_id: parentNodeId,
			derivation_kind: 'canvas_fit', derivation_metadata: derivationMetadata,
		} as PaintResult;
		result = fitted;
		const source = input.trim();
		const saved = await deps.pushHistory({
			...fitted,
			input: source, ddl: ddl ?? '', score: fitted.score, svg: fitted.svg, at: Date.now(),
			elapsed_ms: 0, tokens_in: null, tokens_out: null,
		} as Iteration, {
			sourceText: source, countGeneration: true,
			lineageParentNodeId: parentNodeId, derivationKind: 'canvas_fit', derivationMetadata,
		});
		if (saved?.lineage_node_id && result === fitted) {
			result = { ...fitted, history_id: saved.id, history_at: saved.at, lineage_node_id: saved.lineage_node_id, description_hash: saved.description_hash };
		}
	}

	/** New work. Clearing a text batch also drops its resume panel for good in
	 *  this browser, so that one asks first (author, 2026-11-05). */
	function clearInput() {
		if (inputMode === 'batch' && imageFolder.source !== 'image' && (batch.resume || batch.interrupted)) {
			deps.requestConfirmation({ message: t().batchClearResumeConfirm, runLabel: t().clearInputBtn,
				destructive: true, run: clearInputNow });
			return;
		}
		clearInputNow();
	}

	function clearInputNow() {
		drawChoices[activeDrawTab()] = copyDrawOptions(drawDefaults[activeDrawTab()]);
		if (inputMode === 'single') input = '';
		if (inputMode === 'batch') {
			if (imageFolder.source === 'image') imageFolder.clearInput();
			else batch.clearInput();
		}
		if (inputMode === 'image') clearImage();
		sketchText = null;
		sketchSource = null;
		sketchState = null;
		resetWorkOutput();
	}

	function resetWorkOutput() {
		resetTargetScopedState();
		pipelineController.clear();
		pendingCanvasAspectDerivation = null;
		ddl = null;
		ddlGeneratedBaseline = null;
		thinking = null;
		result = null;
		stage1UserPrompt = '';
		error = null;
		reloadError = null;
		deps.showCanvas();
		elapsedStage1Ms = 0;
		elapsedStage2Ms = 0;
		elapsedTotalMs = 0;
		tokensInStage1 = null;
		tokensOutStage1 = null;
		tokensInStage2 = null;
		tokensOutStage2 = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		canvasViewport.fit();
	}
	const showingDemo = $derived(activeRunMode === 'demo' || (result !== null && result === demo.latestResult && displayedHistoryItem === null));
	return {
		get showingDemo() { return showingDemo; },
		get instructionLang() { return instructionLang; },
		get limitNotesShown() { return limitNotesToShow(result); },
		get singleRunning() { return (activeRunMode === 'single' && loading) || reloading; },
		get ddlEditedAfterGeneration() { return ddlEditedAfterGeneration; },
		get pipelineView() { return pipelineView; },
		get pipelineBusy() { return pipelineBusy; },
		get descriptionLocked() { return descriptionLocked; },
		get pipelinePatch() { return pipelinePatch(pipelineView); },
		get pipelineDiagnostics() { return pipelineDiagnostics(pipelineView, displayedHistoryItem?.pipeline_diagnostics); },
		get pipelineDiagnosticsUnavailable() {
			return pipelineView === null
				&& displayedHistoryItem?.data_warnings?.includes('pipeline_diagnostics_invalid') === true;
		},
		get canSubmit() { return canSubmit; },
		get currentInstructionText() {
			if (displayedHistoryItem?.image_ddl || result?.image_ddl || pipelineView?.image_ddl) return '';
			if (displayedHistoryItem?.input) return displayedHistoryItem.input;
			if (showingDemo) return demo.generatedPrompt;
			if (inputMode === 'batch' || activeRunMode === 'batch') return batch.latestPrompt;
			return input;
		},
		get interpretFallbackReason() { return interpretFallbackReason; },
		get composeFallbackRaw() { return composeFallbackRaw; },
		get composeFallbackDrawnReason() { return composeFallbackReason(composeFallbackRaw); },
		get composeFallbackRecord() { return composeFallbackState(composeFallbackRaw); },
		get statusDdlOrigin() { return (displayedHistoryItem?.display_label ?? null) === 'DDL'; },
		get stage1ModelLabel() {
			return modelDisplayName(tabModelRef('stage1'), deps.models.available(), deps.models.stage1Provider());
		},
		get stage2ModelLabel() {
			return modelDisplayName(tabModelRef('stage2'), deps.models.available(), deps.models.stage2Provider());
		},
		get inputMode() { return inputMode; },
		set inputMode(value) { inputMode = value; },
		get imageProvenance() { return imageProvenance; },
		set imageProvenance(value) { imageProvenance = value; },
		get uploadedImage() { return uploadedImage; },
		get imageFileName() { return imageFileName; },
		get imageUploading() { return imageUploading; },
		get imageRunning() { return imageRunActive || (reloading && !!(displayedHistoryItem?.image_ddl ?? result?.image_ddl)); },
		get imageCanvasAspectId() { return currentOptions().canvas_aspect; },
		set imageCanvasAspectId(value) { if (currentOptions().canvas_aspect !== value) invalidateWorkOptions(); currentOptions().canvas_aspect = value; },
		get drawOptions() { return currentOptions(); },
		tabModelRef,
		tabCatalogSelection,
		get batchTextOptions() { return drawChoices.batch_text; },
		get drawDefaults() { return drawDefaults; },
		setDrawDefaults,
		resetDrawDefaultsOwner: () => { defaultsOwner = null; },
		beginWorkOptions,
		invalidateWorkOptions,
		adoptWorkOptions,
		get imageBeforeReviewDdl() { return imageBeforeReviewDdl(); },
		replayImageBeforeReview,
		selectImage,
		submitImage,
		requestSubmitImage,
		imageFolder,
		runImageFolder,
		clearImage,
		noteImageProvenanceTyped: () => { imageProvenanceTyped = true; },
		get input() { return input; },
		set input(value) { input = value; },
		get stage1UserPrompt() { return stage1UserPrompt; },
		set stage1UserPrompt(value) { stage1UserPrompt = value; },
		get loading() { return loading; },
		set loading(value) { loading = value; },
		get activeRunMode() { return activeRunMode; },
		set activeRunMode(value) { activeRunMode = value; },
		// The composition reading and the laws stage name themselves while they run, on both drawing paths.
		get stageLabel() { return runningStageLabel(stageLabel, activeRunAttempt, t()); },
		set stageLabel(value) { stageLabel = value; },
		get error() { return error; },
		set error(value) { error = value; },
		get reloading() { return reloading; },
		set reloading(value) { reloading = value; },
		get reloadError() { return reloadError; },
		set reloadError(value) { reloadError = value; },
		get replayComparison() { return replayComparison; },
		set replayComparison(value) { replayComparison = value; },
		get ddl() { return ddl; },
		set ddl(value) { ddl = value; },
		get ddlGeneratedBaseline() { return ddlGeneratedBaseline; },
		set ddlGeneratedBaseline(value) { ddlGeneratedBaseline = value; },
		get thinking() { return thinking; },
		set thinking(value) { thinking = value; },
		get result() { return result; },
		set result(value) { result = value; },
		get sketchMode() { return currentOptions().sketch; },
		set sketchMode(value) { if (currentOptions().sketch !== value) invalidateWorkOptions(); currentOptions().sketch = value; },
		get drawRoute() { return currentOptions().route; },
		selectDrawRoute,
		get compositionMode() { return currentOptions().composition; },
		selectCompositionMode,
		get sketchText() { return sketchText; },
		set sketchText(value) { sketchText = value; },
		get sketchSource() { return sketchSource; },
		set sketchSource(value) { sketchSource = value; },
		get sketchState() { return sketchState; },
		set sketchState(value) { sketchState = value; },
		get lineageDetached() { return lineageDetached; },
		set lineageDetached(value) { lineageDetached = value; },
		get pendingCanvasAspectDerivation() { return pendingCanvasAspectDerivation; },
		set pendingCanvasAspectDerivation(value) { pendingCanvasAspectDerivation = value; },
		get elapsedStage1Ms() { return elapsedStage1Ms; },
		set elapsedStage1Ms(value) { elapsedStage1Ms = value; },
		get elapsedStage2Ms() { return elapsedStage2Ms; },
		set elapsedStage2Ms(value) { elapsedStage2Ms = value; },
		get elapsedTotalMs() { return elapsedTotalMs; },
		set elapsedTotalMs(value) { elapsedTotalMs = value; },
		get liveMs() { return liveMs; },
		get tokensInStage1() { return tokensInStage1; },
		set tokensInStage1(value) { tokensInStage1 = value; },
		get tokensOutStage1() { return tokensOutStage1; },
		set tokensOutStage1(value) { tokensOutStage1 = value; },
		get tokensInStage2() { return tokensInStage2; },
		set tokensInStage2(value) { tokensInStage2 = value; },
		get tokensOutStage2() { return tokensOutStage2; },
		set tokensOutStage2(value) { tokensOutStage2 = value; },
		get displayedHistoryItem() { return displayedHistoryItem; },
		set displayedHistoryItem(value) { displayedHistoryItem = value; },
		get activeRunTokensIn() { return activeRunTokensIn; },
		get activeRunTokensOut() { return activeRunTokensOut; },
		get activeRunAttempt() { return activeRunAttempt; },
		get activeRunProgress() { return activeRunProgress; },
		refreshImageBatchResume,
		sketchTextFor,
		adoptSketch,
		currentRefineParent,
		submitWouldRefine,
		confirmFallbackRefine,
		chooseCanvasFit,
		addTokens,
		paintTokensIn,
		paintTokensOut,
		startTimer,
		stopTimer,
		autonomousRuns,
		requestJuxtaposition,
		paintOne,
		pipelineCompatibilityError,
		authorDescription,
		authorDdl,
		selectHistoryAuthority,
		beginNewAuthoring,
		forkPipelineDescription,
		approvePipelinePatch,
		declinePipelinePatch,
		startDemo,
		stopDemo,
		requestSubmit,
		submit,
		submitBatch,
		stopBatch,
		stopReplay,
		stopDdlRender,
		cancelPipelineRun,
		replay,
		clearInput,
	};
}

export type WorkState = ReturnType<typeof createWorkState>;
