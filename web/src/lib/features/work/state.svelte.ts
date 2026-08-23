import { pipelineDescription } from '$lib/description-labels';
import { pluginWarningsToShow } from '$lib/plugin-names';
import { limitNotesToShow } from '$lib/limitNotes';
import { t, getLang } from '$lib/i18n/index.svelte';
import { DEFAULT_SKETCH_MODE, normalizeSketchGrain, normalizeSketchState, sketchGrainOf, sketchModeOf, type SketchMode, type SketchState } from '$lib/sketch';
import { composeFallbackReason, composeFallbackState, composeFallbackValue } from '$lib/composeFallback';
import { needsFallbackRefineConfirm, rememberFallbackRefineConfirm, type FallbackRefineParent } from '$lib/fallbackRefineGate';
import { submitDerivationKind as submitDerivationKindOf, type DerivationKind } from '$lib/derivation';
import { modelDisplayName, qualifiedModelId, type Provider, type ProviderGroup } from '$lib/models';
import { colorCatalogOverride } from '$lib/features/color-catalog/render';
import { colorCatalogSettings } from '$lib/features/color-catalog/settings.svelte';
import { renderSettingsPayload, type RenderOverrides } from '$lib/features/render-payload';
import { runCurrentWork, type InstructionLang, type PaintOptions, type PaintResult } from '$lib/features/run/current-work';
import { batchSettings } from '$lib/features/batch/settings.svelte';
import { wildOverride } from '$lib/features/wild/render';
import type { NumberedLine } from '$lib/features/batch/resume';
import type { CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import type { HistoryItem, Score } from '$lib/historyManagerState.svelte';
import type { ReplayComparison } from '$lib/features/history/replay';
import type { SessionState } from '$lib/features/session/state.svelte';
import { BatchState } from '$lib/features/batch/state.svelte';
import { DemoState } from '$lib/features/demo/state.svelte';
import { RefinementSessionState } from '$lib/features/canvas/refinement-session.svelte';
import { HistoryBrowsingState } from '$lib/features/history/browsing-state.svelte';
import { LineageQueryState } from '$lib/features/history/lineage-state.svelte';
import { CanvasViewportState } from '$lib/features/canvas/viewport-state.svelte';
import type { SaveHistoryOptions } from '$lib/features/history/save';

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
	lineageState: LineageQueryState;
	canvasViewport: CanvasViewportState;
	models: {
		stage1Provider: () => Provider;
		stage1Model: () => string;
		stage2Provider: () => Provider;
		stage2Model: () => string;
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
};

export function createWorkState(deps: WorkStateDeps) {
	const { apiFetch, batch, demo, refinementSession, lineageState, canvasViewport } = deps;
	const { describeApiError, session } = deps;
	const effectiveCanvasAspectId = deps.canvasAspectId;
	const resetTargetScopedState = deps.resetTargetScopedState;
	const ensureVisibleLineageParentId = deps.ensureVisibleLineageParentId;
	const displayLatestBatchRender = deps.displayLatestBatchRender;
	const pushHistory = deps.pushHistory;

	// ── Input ───────────────────────────────────────────────
	const DEFAULT_INPUT = '山の向こうに月が昇る';

	let inputMode = $state<'single' | 'batch' | 'demo'>('single');

	let input = $state(DEFAULT_INPUT);

	let touchSeedText = $state('');

	const instructionLang: InstructionLang = 'auto';

	let stage1UserPrompt = $state('');

	// ── Loading ─────────────────────────────────────────────
	let loading = $state(false);

	let activeRunMode = $state<'single' | 'batch' | 'demo' | null>(null);

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

	// v1.98: ddl is the input side (Stage 1 output or author-written DDL), while
	// expandedDdl is the expanded side (Stage 1.5 output and Stage 2 input).
	// Older records have no input-side value and therefore expose null.
	let expandedDdl = $state<string | null>(null);

	let ddlGeneratedBaseline = $state<string | null>(null);

	let ddlAutoRepairEnabled = $state(true);

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
		 *  screen (model and language comparison): holding the prose fixed is what
		 *  makes those a comparison of models rather than of two different texts. */
	function sketchTextFor(text: string): string | null {
		return sketchText && sketchSource !== null && sketchSource.trim() === text.trim()
			? sketchText
			: null;
	}

	/** What every request that begins at Stage 2 sends. Those paths never run
		 *  0.5 -- they carry the prose the work already has, so the four consumers
		 *  below Stage 1 read what a paint would have given them. */
	function sketchPayloadFor(text: string): Record<string, string> {
		const prose = sketchTextFor(text);
		if (!prose) return {};
		const grain = sketchGrainOf(sketchMode);
		return { sketch_text: prose, ...(grain ? { sketch_grain: grain } : {}) };
	}

	/** Show the prose a run or a saved work was painted from, and select the
		 *  grain it used so a redraw starts from the same place. A work with no
		 *  prose (painted with the layer off, or made before it existed) turns the
		 *  control off rather than silently painting it at the default grain.
		 *
		 *  The control still lands on 'off' for every work with no prose -- what the
		 *  author is going to draw next is a separate question from what the work on
		 *  screen was drawn through. The state is what keeps the two apart: it is
		 *  carried whole, so the note can say "drawn without the layer" and "drawn
		 *  before the layer was recorded" as the different things they are. */
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
		sketchMode = text ? sketchModeOf(normalizeSketchGrain(grain) ?? 'fine') : 'off';
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

	// Which works this screen has already asked about. Kept here and not on the
	// server: the question is about this sitting, not about the work (contract
	// §5-7). See $lib/fallbackRefineGate.
	const fallbackRefineAsked = new Set<string>();
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

	async function requestVisionRefineAdvice(historyId: string, model: string, instruction: string, direction: string, enabledKinds: string[], signal: AbortSignal) {
		const r = await apiFetch('/api/refine/vision-advice', {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ history_id: historyId, model, instruction, direction, enabled_kinds: enabledKinds, language: getLang() })
		});
		if (!r.ok) {
			const data = await r.json().catch(() => ({})) as { detail?: unknown; };
			throw new Error(describeApiError(data.detail, r.status));
		}
		return await r.json() as { observation: string; next_direction: string; suggested_kind: string; model: string; };
	}

	async function paintOne(text: string, options: PaintOptions = {}): Promise<{ ddl: string; thinking: string | null; } & PaintResult> {
		return runCurrentWork(
			text,
			options,
			{
				uiLang: getLang(),
				strings: t(),
				// Resolve page settings before crossing the feature boundary. A
				// caller's one-run override still wins inside the coordinator.
				stage1Model: qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model()),
				stage2Model: qualifiedModelId(deps.models.stage2Provider(), deps.models.stage2Model()),
				includeThinking: deps.models.includeThinking(),
				instructionLang,
				canvasAspectId: effectiveCanvasAspectId(),
				ddlAutoRepairEnabled,
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
				loadNearbyHistory: lineageState.loadNearby,
				attachSavedLineage: () => { lineageDetached = false; },
				updateGenerationCount: (count) => session.updateGenerationCount(count)
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
				expand_intermediate: true,
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: unknown; };
			throw new Error(describeApiError(d.detail, r.status));
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
		// Expanded DDL passed to Stage 2 (v1.98).
		ddl?: string | null;
		source_ddl?: string | null;
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
		render_seed?: number | null;
		render_wild?: boolean | null;
		composition_seed?: number | null;
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
				auto_repair: ddlAutoRepairEnabled,
				...renderSettingsPayload('compose', renderOptions.renderOverrides),
				...(renderOptions.lineageParentNodeId ? { lineage_parent_node_id: renderOptions.lineageParentNodeId } : {}),
			})
		});
		if (!r.ok) {
			const d = await r.json().catch(() => ({})) as { detail?: unknown; };
			throw new Error(describeApiError(d.detail, r.status));
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
			render_seed?: number | null;
			render_wild?: boolean | null;
			composition_seed?: number | null;
			elapsed_ms: number;
			tokens_in: number | null;
			tokens_out: number | null;
		};
		return data;
	}

	async function startDemo() {
		if (loading || refinementSession.gridBusy) return;
		clearInput();
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
			paintInstruction: (prompt, paintOptions) => paintOne(prompt, paintOptions),
			onLatestResult: (painted) => {
				const sourceDdl = painted.source_ddl ?? painted.ddl;
				ddl = sourceDdl;
				expandedDdl = painted.ddl;
				ddlGeneratedBaseline = sourceDdl;
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
	async function submit(options: { resumeLines?: NumberedLine[]; } = {}) {
		if (!canSubmit || loading || refinementSession.gridBusy) return;
		// Ask before resetTargetScopedState and before any intermediate save.
		if (submitWouldRefine() && !(await confirmFallbackRefine(currentRefineParent()))) return;
		resetTargetScopedState();
		try {
			await ensureVisibleLineageParentId();
		} catch (cause) {
			error = cause instanceof Error ? cause.message : String(cause);
			return;
		}

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
		const submitParentGrain = normalizeSketchGrain(displayedHistoryItem?.sketch_grain);
		const submitGrain = sketchGrainOf(sketchMode);
		const submitGrainChanged = submitGrain !== submitParentGrain;
		const submitDerivationKind: DerivationKind | null = submitDerivationKindOf({
			hasParent: submitParentNodeId !== null,
			canvasAspectChanged: canvasAspectDerivation !== null,
			textChanged: submitTextChanged,
			grainChanged: submitGrainChanged
		});
		// A redraw at the same grain replays the prose it was painted from; the
		// layer is not deterministic, so calling it again would not be a replay.
		// An edited prose wins over the stored one, and a changed grain has to be
		// written anew.
		const sketchEdited = sketchDraft.trim() !== '' && sketchDraft.trim() !== (sketchText ?? '').trim();
		const submitSketchText = sketchEdited
			? sketchDraft.trim()
			: (!submitTextChanged && !submitGrainChanged ? sketchText : null);
		const submitDerivationMetadata = canvasAspectDerivation
			? { from_canvas_aspect: canvasAspectDerivation.fromAspectId, to_canvas_aspect: canvasAspectDerivation.toAspectId }
			: {};

		loading = true; error = null;
		activeRunMode = 'single';
		ddl = null; expandedDdl = null; ddlGeneratedBaseline = null; thinking = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		startTimer();

		try {
			stageLabel = t().stageDdlGenerating;
			const r = await paintOne(input, {
				sourceText: input,
				canvasAspectId: effectiveCanvasAspectId(),
				lineageParentNodeId: submitParentNodeId,
				sketchText: submitSketchText,
				derivationKind: submitDerivationKind,
				derivationMetadata: submitDerivationMetadata,
				signal: abortController.signal,
				onStage1: (stage1) => {
					elapsedStage1Ms = stage1.elapsed_ms;
					tokensInStage1 = stage1.tokens_in;
					tokensOutStage1 = stage1.tokens_out;
					ddl = stage1.ddl;
					expandedDdl = null;
					ddlGeneratedBaseline = stage1.ddl;
					thinking = stage1.thinking;
					stageLabel = t().stageImageGenerating;
					reloading = true;
				}
			});
			if (submitStopRequested) return;
			reloading = false;
			elapsedStage1Ms = r.elapsed_stage1_ms;
			elapsedStage2Ms = r.elapsed_stage2_ms;
			elapsedTotalMs = r.elapsed_total_ms;
			tokensInStage1 = r.tokens_in_stage1;
			tokensOutStage1 = r.tokens_out_stage1;
			tokensInStage2 = r.tokens_in_stage2;
			tokensOutStage2 = r.tokens_out_stage2;
			ddl = r.source_ddl ?? r.ddl;
			expandedDdl = r.ddl;
			ddlGeneratedBaseline = ddl;
			thinking = r.thinking;
			result = r; deps.showCanvas();
			adoptSketch(r.sketch_text ?? null, r.sketch_grain, input, r.sketch_state);
			canvasViewport.fit();
			if (r.history_id && submitAbortController === abortController && !submitStopRequested) {
				if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
				lineageDetached = false;
				await deps.history().fetchOffset(0, { anchorId: r.history_id });
				displayedHistoryItem = deps.history().items.find((item) => item.id === r.history_id) ?? null;
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

	async function submitBatch(options: { resumeLines?: NumberedLine[]; }): Promise<void> {
		const batchCanvasAspectId = effectiveCanvasAspectId();
		const batchCatalogId = colorCatalogSettings.selected;
		loading = true; error = null;
		activeRunMode = 'batch';
		ddl = null; expandedDdl = null; ddlGeneratedBaseline = null; thinking = null;
		displayedHistoryItem = null;
		deps.history().clearSelection();
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		deps.showCanvas();
		startTimer();

		try {
			await batch.run({
				resumeLines: options.resumeLines,
				canvasAspectId: batchCanvasAspectId,
				renderOverrides: colorCatalogOverride(batchCatalogId),
				maxRetries: batchSettings.maxRetries,
				paintLine: (text, paintOptions) => paintOne(text, paintOptions),
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
		if (activeRunMode === 'batch') {
			batch.stop();
			return;
		}
		if (activeRunMode !== 'single') return;
		submitStopRequested = true;
		submitAbortController?.abort();
	}

	function stopReplay() {
		if (!reloading) return;
		replayStopRequested = true;
		replayAbortController?.abort();
	}

	function stopDdlRender() {
		if (replayAbortController) {
			stopReplay();
			return;
		}
		stopBatch();
	}

	// ── Replay (Stage 2 only) ───────────────────────────────
	async function replay() {
		if (!ddl || reloading) return;
		if (submitWouldRefine() && !(await confirmFallbackRefine(currentRefineParent()))) return;
		resetTargetScopedState();
		try {
			await ensureVisibleLineageParentId();
		} catch (cause) {
			reloadError = cause instanceof Error ? cause.message : String(cause);
			return;
		}
		const canvasAspectDerivation = pendingCanvasAspectDerivation;
		const replayParentNodeId = canvasAspectDerivation?.parentNodeId ?? (lineageDetached ? null : (displayedHistoryItem?.lineage_node_id ?? result?.lineage_node_id ?? null));
		const replayKind: DerivationKind | null = canvasAspectDerivation
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
		const uiLang = getLang();
		const replayInput = input;
		const startedAt = Date.now();
		elapsedStage1Ms = 0; elapsedStage2Ms = 0; elapsedTotalMs = 0;
		tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = null; tokensOutStage2 = null;
		stageLabel = t().stageStructuring('');
		startTimer();
		try {
			const resolvedStage2Model = qualifiedModelId(deps.models.stage2Provider(), deps.models.stage2Model());
			const r = await apiFetch('/api/compose', {
				method: 'POST',
				signal: abortController.signal,
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					ddl,
					model: resolvedStage2Model,
					description: replayInput,
					...sketchPayloadFor(replayInput),
					instruction_lang: instructionLang,
					ui_lang: uiLang,
					canvas_aspect: effectiveCanvasAspectId(),
					auto_repair: ddlAutoRepairEnabled,
					...renderSettingsPayload('compose')
				})
			});
			if (!r.ok) {
				const d = await r.json().catch(() => ({})) as { detail?: unknown; };
				throw new Error(describeApiError(d.detail, r.status));
			}
			const d = await r.json() as {
				score: Score;
				svg: string;
				stage2_model?: string | null;
				render_build_number?: string | null;
				render_color_profile?: Record<string, string> | null;
				render_engine_id?: string | null;
				render_engine_version?: string | null;
				render_color_catalog_id?: string | null;
				render_color_catalog_name?: string | null;
				render_color_catalog_sub?: string | null;
				render_color_map?: Record<string, string> | null;
				render_canvas_aspect?: string | null;
				render_canvas_aspect_id?: string | null;
				render_canvas_aspect_ratio?: number | null;
				render_seed?: number | null;
				render_wild?: boolean | null;
				composition_seed?: number | null;
				instruction_lang_requested?: string | null;
				instruction_lang_resolved?: string | null;
				ui_lang?: string | null;
				render_hash?: string | null;
				render_hash_short?: string | null;
				tokens_in: number | null;
				tokens_out: number | null;
			};
			const elapsedMs = Date.now() - startedAt;
			const resolvedStage1Model = result?.stage1_model ?? qualifiedModelId(deps.models.stage1Provider(), deps.models.stage1Model());
			const savedStage2Model = d.stage2_model ?? resolvedStage2Model;
			const replayMetadata = {
				render_build_number: d.render_build_number,
				render_color_profile: d.render_color_profile,
				render_engine_id: d.render_engine_id,
				render_engine_version: d.render_engine_version,
				render_color_catalog_id: d.render_color_catalog_id,
				render_color_catalog_name: d.render_color_catalog_name,
				render_color_catalog_sub: d.render_color_catalog_sub,
				render_color_map: d.render_color_map,
				render_canvas_aspect: d.render_canvas_aspect,
				render_canvas_aspect_id: d.render_canvas_aspect_id,
				render_canvas_aspect_ratio: d.render_canvas_aspect_ratio,
				render_seed: d.render_seed,
				composition_seed: d.composition_seed,
				instruction_lang_requested: d.instruction_lang_requested,
				instruction_lang_resolved: d.instruction_lang_resolved,
				ui_lang: d.ui_lang,
				render_hash: d.render_hash,
				render_hash_short: d.render_hash_short
			};
			result = result
				? { ...result, score: d.score, svg: d.svg, stage2_model: savedStage2Model, ...replayMetadata }
				: { score: d.score, svg: d.svg, stage1_model: resolvedStage1Model, stage2_model: savedStage2Model, ...replayMetadata, elapsed_stage1_ms: 0, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			if (result) {
				result = { ...result, elapsed_stage2_ms: elapsedMs, elapsed_total_ms: elapsedMs, tokens_in_stage2: d.tokens_in, tokens_out_stage2: d.tokens_out };
			}
			elapsedStage1Ms = 0; elapsedStage2Ms = elapsedMs; elapsedTotalMs = elapsedMs;
			tokensInStage1 = null; tokensOutStage1 = null; tokensInStage2 = d.tokens_in; tokensOutStage2 = d.tokens_out;
			const savedHistory = await pushHistory({
				input: replayInput,
				ddl,
				score: d.score,
				svg: d.svg,
				at: Date.now(),
				elapsed_ms: elapsedMs,
				stage1_model: resolvedStage1Model,
				stage2_model: savedStage2Model,
				tokens_in: d.tokens_in,
				tokens_out: d.tokens_out,
				catalog_id: colorCatalogSettings.effectiveId !== 'default' ? colorCatalogSettings.effectiveId : null
			}, { selectSaved: true, sourceText: replayInput, lineageParentNodeId: replayParentNodeId, derivationKind: replayKind, derivationMetadata: replayDerivationMetadata });
			if (savedHistory && result) {
				if (canvasAspectDerivation) pendingCanvasAspectDerivation = null;
				lineageDetached = false;
				displayedHistoryItem = savedHistory;
				result = {
					...result,
					history_id: savedHistory.id,
					history_at: savedHistory.at,
					render_hash: savedHistory.render_hash,
					render_hash_short: savedHistory.render_hash_short,
				};
			}
			deps.showCanvas();
			canvasViewport.fit();
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

	function clearInput() {
		resetTargetScopedState();
		pendingCanvasAspectDerivation = null;
		if (inputMode === 'single') input = '';
		if (inputMode === 'batch') batch.clearInput();
		if (inputMode === 'demo') demo.clearInput();
		ddl = inputMode === 'single' ? '' : null;
		expandedDdl = null;
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
	return {
		get instructionLang() { return instructionLang; },
		get pluginWarningsShown() { return pluginWarningsToShow(result); },
		get limitNotesShown() { return limitNotesToShow(result); },
		get singleRunning() { return (activeRunMode === 'single' && loading) || reloading; },
		get ddlEditedAfterGeneration() { return ddlEditedAfterGeneration; },
		get canSubmit() { return canSubmit; },
		get currentInstructionText() {
			if (displayedHistoryItem?.input) return displayedHistoryItem.input;
			if (inputMode === 'demo' || activeRunMode === 'demo') return demo.generatedPrompt;
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
		get input() { return input; },
		set input(value) { input = value; },
		get touchSeedText() { return touchSeedText; },
		set touchSeedText(value) { touchSeedText = value; },
		get stage1UserPrompt() { return stage1UserPrompt; },
		set stage1UserPrompt(value) { stage1UserPrompt = value; },
		get loading() { return loading; },
		set loading(value) { loading = value; },
		get activeRunMode() { return activeRunMode; },
		set activeRunMode(value) { activeRunMode = value; },
		get stageLabel() { return stageLabel; },
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
		get expandedDdl() { return expandedDdl; },
		set expandedDdl(value) { expandedDdl = value; },
		get ddlGeneratedBaseline() { return ddlGeneratedBaseline; },
		set ddlGeneratedBaseline(value) { ddlGeneratedBaseline = value; },
		get ddlAutoRepairEnabled() { return ddlAutoRepairEnabled; },
		set ddlAutoRepairEnabled(value) { ddlAutoRepairEnabled = value; },
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
		sketchTextFor,
		sketchPayloadFor,
		adoptSketch,
		currentRefineParent,
		submitWouldRefine,
		confirmFallbackRefine,
		addTokens,
		paintTokensIn,
		paintTokensOut,
		startTimer,
		stopTimer,
		requestVisionRefineAdvice,
		paintOne,
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
		replay,
		clearInput,
	};
}

export type WorkState = ReturnType<typeof createWorkState>;
