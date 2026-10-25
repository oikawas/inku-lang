import { pipelineDescription } from '$lib/description-labels';
import { hasDdlBody } from '$lib/ddl-source';
import { pluginWarningsToShow } from '$lib/plugin-names';
import { limitNotesToShow } from '$lib/limitNotes';
import { t, getLang } from '$lib/i18n/index.svelte';
import { DEFAULT_SKETCH_MODE, normalizeSketchState, type SketchMode, type SketchState } from '$lib/sketch';
import { composeFallbackReason, composeFallbackState, composeFallbackValue } from '$lib/composeFallback';
import { needsFallbackRefineConfirm, rememberFallbackRefineConfirm, type FallbackRefineParent } from '$lib/fallbackRefineGate';
import { submitDerivationKind as submitDerivationKindOf, type DerivationKind } from '$lib/derivation';
import { modelDisplayName, qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
import { AUTO_CATALOG_ID, colorCatalogOverride } from '$lib/features/color-catalog/render';
import { colorCatalogSettings } from '$lib/features/color-catalog/settings.svelte';
import { renderSettingsPayload, type RenderOverrides } from '$lib/features/render-payload';
import { runCurrentWork, type InstructionLang, type PaintOptions, type PaintResult, type Seed } from '$lib/features/run/current-work';
import { batchSettings } from '$lib/features/batch/settings.svelte';
import { wildOverride } from '$lib/features/wild/render';
import { wildSettings } from '$lib/features/wild/settings.svelte';
import type { NumberedLine } from '$lib/features/batch/resume';
import { getCanvasAspectOption, type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import { canvasRatioLabel, canvasRatioOfAspect, declaredCanvasRatio, sameCanvasRatio, type CanvasRatio } from '$lib/canvas-ratio';
import type { HistoryItem, Score } from '$lib/historyManagerState.svelte';
import type { ReplayComparison } from '$lib/features/history/replay';
import type { JuxtapositionResult } from '$lib/features/juxtaposition/juxtaposition';
import type { AutonomousRun, AutonomousRunsApi } from '$lib/features/autonomous/runs';
import type { SessionState } from '$lib/features/session/state.svelte';
import { BatchState } from '$lib/features/batch/state.svelte';
import { ImageFolderBatch } from '$lib/features/batch/image-folder.svelte';
import { isConnectionFailure } from '$lib/transport/connection-failure';
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
	let imageCanvasAspectId = $state<CanvasAspectId>('image');
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
			pipelineController.clear();
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

	let result = $state<PaintResult | null>(null);

	// Sketching (Stage 0.5). Chosen per draw, so it is plain state -- not persisted the
	// way a user setting like the color catalog is (contract section 0.3.1).
	let sketchMode = $state<SketchMode>(DEFAULT_SKETCH_MODE);

	// The prose the layer wrote for the run on screen, and the author's edit of
	// it. Editing and painting again sends the edited prose instead of calling
	// the layer, so what the author reads is what Stage 1 reads.
	let sketchText = $state<string | null>(null);

	// Which description the prose was written for. Prose written for one text is
	// not prose for another, and the description can be edited after a run.
	let sketchSource = $state<string | null>(null);

	let sketchDraft = $state('');

	let sketchEditing = $state(false);

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
			? sketchDraft
			: null;
	}

	/** What every request that begins at Stage 2 sends. Those paths never ask
	 *  for a sketch -- they carry the one the work already has. */
	function sketchPayloadFor(text: string): Record<string, string> {
		const prose = sketchTextFor(text);
		return prose ? { sketch_text: prose } : {};
	}

	/** Show the sketch a run or a saved work was painted with, and turn the
	 *  control on for a work that has one so a redraw starts from the same
	 *  place; any other work leaves the control off.
	 *
	 *  What the author is going to draw next is a separate question from what
	 *  the work on screen was drawn through. The state is what keeps the two
	 *  apart: it is carried whole, so the note can say "drawn without the layer",
	 *  "the description needed no sketch" and "drawn before the layer was
	 *  recorded" as the different things they are. */
	function adoptSketch(
		text: string | null,
		grain: unknown,
		source: string | null = null,
		state: unknown = null
	): void {
		sketchText = text;
		sketchSource = source;
		sketchDraft = text ?? '';
		sketchEditing = false;
		void grain;
		sketchState = normalizeSketchState(state);
		sketchMode = text ? 'on' : DEFAULT_SKETCH_MODE;
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
		const render = renderSettingsPayload('paint', options.renderOverrides);
		return {
			sketch: options.sketchMode ?? sketchMode,
			...(options.sketchText ? { sketch_text: options.sketchText } : {}),
			stage1_model: options.stage1Model ?? qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model()),
			stage2_model: options.stage2Model ?? qualifiedModelId(deps.models.stage2Provider(), deps.models.stage2Model()),
			instruction_lang: instructionLang,
			ui_lang: getLang(),
			catalog_id: typeof render.catalog_id === 'string' ? render.catalog_id : colorCatalogSettings.effectiveId,
			catalog_mode: typeof render.catalog_mode === 'string' ? render.catalog_mode : undefined,
			canvas_aspect: options.canvasAspectId ?? effectiveCanvasAspectId(),
			...(options.canvasFit ? { canvas_fit: options.canvasFit } : {}),
			render_seed: options.renderSeed,
			composition_seed: options.compositionSeed,
			wild: typeof render.wild === 'boolean' ? render.wild : undefined,
			history_display_label: options.displayLabel,
			batch_line_number: options.batchLineNumber,
			batch_run_id: options.batchRunId,
			history_visibility: options.historyVisibility,
			lineage_parent_node_id: options.lineageParentNodeId ?? undefined,
			derivation_kind: options.derivationKind ?? undefined,
			derivation_metadata: options.derivationMetadata,
			...(options.importedPlugins?.length ? { imported_plugins: options.importedPlugins } : {}),
			count_generation: options.countGeneration ?? true,
		};
	}

	function adoptPipelineView(view: PipelineView | null): void {
		pipelineView = view;
		activeRunAttempt = view?.provider_attempt ?? null;
		if (!view) return;
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
		const model = qualifiedModelId(deps.models.visionProvider(), deps.models.visionModel());
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
			const view = await finishPipeline(() => pipelineController.fromImage(image.image_id, provenance, imageCanvasAspectId, {
				...pipelineOptions(), stage1_model: model, stage2_model: model,
				sketch: 'off', sketch_text: undefined, wild: false, instruction_lang: 'ja',
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
	);

	async function paintPictureFile(file: File, signal: AbortSignal): Promise<void> {
		const api = new PipelineApi(apiFetch);
		const provenance = await provenanceOfFile(file);
		const image = await api.uploadImage(file, signal);
		signal.throwIfAborted();
		const model = qualifiedModelId(deps.models.visionProvider(), deps.models.visionModel());
		stageLabel = t().imageWritingDdl;
		const view = await imageBatchController.fromImage(image.image_id, provenance, imageCanvasAspectId, {
			...pipelineOptions(), stage1_model: model, stage2_model: model,
			sketch: 'off', sketch_text: undefined, wild: false, instruction_lang: 'ja',
			canvas_aspect: imageCanvasAspectId === 'image' ? image.nearest_format_id : imageCanvasAspectId,
			canvas_fit: 'contain',
		}, signal);
		activeRunAttempt = null;
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
		try {
			await imageFolder.run({
				fromStart,
				paintPicture: paintPictureFile,
				stopsTheRun: pictureRunLost,
				describe: (cause) => cause instanceof PipelineApiError ? describeApiError(cause.detail, cause.status)
					: cause instanceof Error ? cause.message : String(cause),
			});
		} finally {
			stopTimer(); loading = false; activeRunMode = null; stageLabel = '';
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
			if (view.result?.history_id) {
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
		}
	}

	function selectLegacyHistory(historyId: string): void {
		if (pipelineView?.result?.history_id === historyId) return;
		pipelineController.markLegacy(historyId);
	}

	function selectHistoryAuthority(historyId: string, variationId?: string | null, signal?: AbortSignal): Promise<boolean> {
		return pipelineController.selectHistory(historyId, variationId, signal);
	}

	function beginNewAuthoring(): void {
		pipelineController.clear();
	}

	async function authorDescription(text: string, options: PaintOptions = {}, signal?: AbortSignal): Promise<PipelineView> {
		// An edited sketch for this very description is drawn as it stands.
		const mode = options.sketchMode ?? sketchMode;
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
	const interpretFallbackReason = $derived(
		displayedHistoryItem
			? (displayedHistoryItem.interpret_fallback ?? null)
			: (result?.interpret_fallback_used ? (result.interpret_fallback_reasons?.[0] ?? 'stage1_fallback') : null)
	);
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
		if (!options.batchRunId) pipelineController.clear();
		return runCurrentWork(
			text,
			options,
			{
				uiLang: getLang(),
				strings: t(),
				// Resolve injected route settings before entering the stateless run
				// operation. A caller's one-run override still wins there.
				stage1Model: qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model()),
				stage2Model: qualifiedModelId(deps.models.stage2Provider(), deps.models.stage2Model()),
				includeThinking: deps.models.includeThinking(),
				instructionLang,
				canvasAspectId: effectiveCanvasAspectId(),
				sketchMode,
				renderPayload: renderSettingsPayload('paint', options.renderOverrides)
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
				adoptPipelineView: options.batchRunId ? undefined : (view) => pipelineController.adopt(view),
				setProviderAttempt: (attempt) => { activeRunAttempt = attempt; }
			}
		);
	}

	type InterpretResult = {
		ddl: string;
		thinking: string | null;
		tokens_in: number | null;
		tokens_out: number | null;
	};

	async function interpretOne(text: string, signal?: AbortSignal, modelOverride?: string, langOverride?: InstructionLang): Promise<InterpretResult> {
		const uiLang = getLang();
		stage1UserPrompt = text;
		const resolvedStage1Model = modelOverride ?? qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model());
		const r = await apiFetch('/api/interpret', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				description: text,
				...(sketchTextFor(text) ? { sketch_text: sketchTextFor(text) } : {}),
				model: resolvedStage1Model,
				include_thinking: deps.models.includeThinking(),
				instruction_lang: langOverride ?? instructionLang,
				ui_lang: uiLang,
			})
		});
		if (!r.ok) {
			throw await pipelineCompatibilityError(r);
		}
		const data = await r.json() as {
			ddl: string;
			thinking: string | null;
			tokens_in?: number | null;
			tokens_out?: number | null;
		};
		return {
			ddl: data.ddl,
			thinking: data.thinking,
			tokens_in: data.tokens_in ?? null,
			tokens_out: data.tokens_out ?? null,
		};
	}

	async function composeOne(currentDdl: string, originalText: string, signal?: AbortSignal, modelOverride?: string, langOverride?: InstructionLang, renderOptions: { canvasAspectId?: CanvasAspectId; lineageParentNodeId?: string | null; renderOverrides?: RenderOverrides; } = {}): Promise<{
		score: Score;
		svg: string;
		// The persisted source used for display, editing, and replay.
		ddl?: string | null;
		stage2_model?: string | null;
		render_build_number?: string | null;
		render_color_profile?: Record<string, string> | null;
		render_engine_id?: string | null;
		render_engine_version?: string | null;
		render_hash?: string | null;
		render_hash_short?: string | null;
		render_color_catalog_id?: string | null;
		render_color_catalog_name?: string | null;
		render_color_catalog_sub?: string | null;
		render_color_map?: Record<string, string> | null;
		render_canvas_aspect?: string | null;
		render_canvas_aspect_id?: string | null;
		render_canvas_aspect_ratio?: number | null;
		render_seed?: Seed | null;
		render_wild?: boolean | null;
		composition_seed?: Seed | null;
		instruction_lang_requested?: string | null;
		instruction_lang_resolved?: string | null;
		ui_lang?: string | null;
		elapsed_ms: number;
		tokens_in: number | null;
		tokens_out: number | null;
		sketch_text?: string | null;
		sketch_grain?: string | null;
		sketch_state?: string | null;
	}> {
		const uiLang = getLang();
		const resolvedStage2Model = modelOverride ?? qualifiedModelId(deps.models.stage2Provider(), deps.models.stage2Model());
		const r = await apiFetch('/api/compose', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				ddl: currentDdl,
				model: resolvedStage2Model,
				description: originalText,
				...sketchPayloadFor(originalText),
				instruction_lang: langOverride ?? instructionLang,
				ui_lang: uiLang,
				canvas_aspect: renderOptions.canvasAspectId ?? effectiveCanvasAspectId(),
				...renderSettingsPayload('compose', renderOptions.renderOverrides),
				...(renderOptions.lineageParentNodeId ? { lineage_parent_node_id: renderOptions.lineageParentNodeId } : {}),
			})
		});
		if (!r.ok) {
			throw await pipelineCompatibilityError(r);
		}
		const data = await r.json() as {
			score: Score;
			svg: string;
			stage2_model?: string | null;
			render_build_number?: string | null;
			render_color_profile?: Record<string, string> | null;
			render_engine_id?: string | null;
			render_engine_version?: string | null;
			render_hash?: string | null;
			render_hash_short?: string | null;
			render_color_catalog_id?: string | null;
			render_color_catalog_name?: string | null;
			render_color_catalog_sub?: string | null;
			render_color_map?: Record<string, string> | null;
			render_canvas_aspect?: string | null;
			render_canvas_aspect_id?: string | null;
			render_canvas_aspect_ratio?: number | null;
			render_seed?: Seed | null;
			render_wild?: boolean | null;
			composition_seed?: Seed | null;
			elapsed_ms: number;
			tokens_in: number | null;
			tokens_out: number | null;
		};
		return data;
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
				...colorCatalogOverride(colorCatalogSettings.selected),
				...wildOverride(false),
			}),
			paintInstruction: (prompt, paintOptions) => {
				const model = qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model());
				return paintOne(prompt, { ...paintOptions, stage1Model: model, stage2Model: model });
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
			stageLabel = t().stageDdlGenerating;
			const view = await authorDescription(input, {
				sourceText: input,
				canvasAspectId: effectiveCanvasAspectId(),
				lineageParentNodeId: submitParentNodeId,
				derivationKind: submitDerivationKind,
				derivationMetadata: submitDerivationMetadata,
			}, abortController.signal);
			if (submitStopRequested) return;
			if (view.result?.history_id && submitAbortController === abortController && !submitStopRequested) {
				if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
				lineageDetached = false;
			}
		} catch (cause) {
			if (!(submitStopRequested || abortController.signal.aborted)) {
				error = cause instanceof Error ? cause.message : String(cause);
				result = null;
			}
		} finally {
			if (submitAbortController === abortController) submitAbortController = null;
			submitStopRequested = false;
			stopTimer(); loading = false; reloading = false; activeRunMode = null; stageLabel = '';
		}
	}

	async function submitBatch(options: { resumeLines?: NumberedLine[]; retryFailedLines?: NumberedLine[]; }): Promise<void> {
		const batchCanvasAspectId = effectiveCanvasAspectId();
		const batchCatalogId = colorCatalogSettings.selected;
		const batchStage1Model = qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model());
		const batchStage2Model = qualifiedModelId(deps.models.stage2Provider(), deps.models.stage2Model());
		const batchSketchMode = sketchMode;
		const batchWild = wildSettings.enabled;
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
				},
				canvasAspectId: batchCanvasAspectId,
				renderOverrides: { ...colorCatalogOverride(batchCatalogId), ...wildOverride(batchWild) },
				maxRetries: batchSettings.maxRetries,
				paintLine: (text, paintOptions) => paintOne(text, {
					...paintOptions, stage1Model: batchStage1Model, stage2Model: batchStage2Model,
					sketchMode: batchSketchMode,
				}),
				onLatestResult: (painted) => {
					thinking = painted.thinking;
					if (inputMode === 'batch' && batch.autoFollowLatest) displayLatestBatchRender();
				},
				onPaintComplete: () => { elapsedTotalMs = Date.now() - _timerStart; },
				refreshAfterServerSave: () => deps.history().refreshAfterServerSave(),
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

	function clearInput() {
		if (inputMode === 'single') input = '';
		if (inputMode === 'batch') batch.clearInput();
		resetWorkOutput();
	}

	function resetWorkOutput() {
		resetTargetScopedState();
		pipelineController.clear();
		pendingCanvasAspectDerivation = null;
		ddl = inputMode === 'single' ? '' : null;
		ddlGeneratedBaseline = inputMode === 'single' ? '' : null;
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
		get pluginWarningsShown() { return pluginWarningsToShow(result); },
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
			return modelDisplayName(qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model()), deps.models.available(), deps.models.stage1Provider());
		},
		get stage2ModelLabel() {
			return modelDisplayName(qualifiedModelId(deps.models.stage2Provider(), deps.models.stage2Model()), deps.models.available(), deps.models.stage2Provider());
		},
		get inputMode() { return inputMode; },
		set inputMode(value) { inputMode = value; },
		get imageProvenance() { return imageProvenance; },
		set imageProvenance(value) { imageProvenance = value; },
		get uploadedImage() { return uploadedImage; },
		get imageFileName() { return imageFileName; },
		get imageUploading() { return imageUploading; },
		get imageRunning() { return imageRunActive || (reloading && !!(displayedHistoryItem?.image_ddl ?? result?.image_ddl)); },
		get imageCanvasAspectId() { return imageCanvasAspectId; },
		set imageCanvasAspectId(value) { imageCanvasAspectId = value; },
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
		get sketchMode() { return sketchMode; },
		set sketchMode(value) { sketchMode = value; },
		get sketchText() { return sketchText; },
		set sketchText(value) { sketchText = value; },
		get sketchSource() { return sketchSource; },
		set sketchSource(value) { sketchSource = value; },
		get sketchDraft() { return sketchDraft; },
		set sketchDraft(value) { sketchDraft = value; },
		get sketchEditing() { return sketchEditing; },
		set sketchEditing(value) { sketchEditing = value; },
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
		sketchTextFor,
		sketchPayloadFor,
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
		selectLegacyHistory,
		selectHistoryAuthority,
		beginNewAuthoring,
		forkPipelineDescription,
		approvePipelinePatch,
		declinePipelinePatch,
		interpretOne,
		composeOne,
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
