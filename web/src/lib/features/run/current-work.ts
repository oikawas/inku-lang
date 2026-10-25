import type { ImportedPlugin } from '$lib/features/ddl-editor/ddl-import';
import type { DerivationKind } from '../../derivation.ts';
import { interpretationFeedback } from '../../highlight.ts';
import type { LangPack } from '../../i18n/types.ts';
import {
	paintStageHandlers,
	paintStageLabel,
	readPaintStream,
	type PaintStage1Event,
	type ProviderAttemptCount
} from '../../paintStream.ts';
import type { CanvasAspectId } from '../../plugins/system/canvas-aspect/index.ts';
import { type SketchMode } from '../../sketch.ts';
import type { DescriptionDdlRecord, DrawRoute } from '../../draw-route.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import { ConnectionFailure, GATEWAY_STATUSES, isAbort } from '../../transport/connection-failure.ts';
import type { RenderOverrides } from '../render-payload.ts';
import type { Recomposition } from '../canvas/recomposition.ts';
import type { ProviderUsage } from '../canvas/generation-info-tokens.ts';
import { pipelineViewFromErrorDetail, type PipelineView } from '../pipeline/api.ts';

export type InstructionLang = 'auto' | 'ja' | 'en';

export type PaintScore = {
	instructions: unknown[];
	canvas?: string | null;
};

/**
 * A seed as the API carries it: a decimal string, exact past 2^53 (a seed drawn
 * from seed text has 64 bits), or a number the Web drew itself. Send it back as
 * it came; `Number()` rounds a long one, and a rounded seed draws another picture.
 */
export type Seed = number | string;

export type PaintResult = {
	image_ddl?: Record<string, unknown> | null;
	/** Read and draw's record (SPEC 12.6.7); null on any other work. */
	description_ddl?: DescriptionDdlRecord | null;
	/** The tokens by stage (2026-10-26); null when the drawing sent nothing. */
	provider_usage?: ProviderUsage | null;
	image_provenance?: string | null;
	svg: string;
	score: PaintScore;
	stage1_model?: string | null;
	stage2_model?: string | null;
	render_build_number?: string | null;
	render_color_profile?: Record<string, string> | null;
	render_engine_id?: string | null;
	render_engine_version?: string | null;
	ddl_version?: string | null;
	ddl_engine_version?: string | null;
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
	recomposition?: Recomposition | null;
	interpretation_seed?: string | null;
	seed_text?: string | null;
	sketch_text?: string | null;
	sketch_grain?: string | null;
	sketch_fallback_used?: boolean;
	sketch_state?: string | null;
	instruction_lang_requested?: string | null;
	instruction_lang_resolved?: string | null;
	ui_lang?: string | null;
	history_id?: string | null;
	history_at?: number | null;
	description_hash?: string | null;
	lineage_node_id?: string | null;
	lineage_parent_node_id?: string | null;
	derivation_kind?: DerivationKind | null;
	derivation_metadata?: Record<string, unknown>;
	elapsed_stage1_ms: number;
	elapsed_stage2_ms: number;
	elapsed_total_ms: number;
	// Compatibility diagnostics returned for older saved work.
	plugin_warnings?: string[] | null;
	// Which render limits took effect and where they came from. The values say
	// what was used; the source distinguishes a replayed ceiling (ledger I-154).
	render_limits?: Record<string, number> | null;
	render_limits_source?: string | null;
	render_limit_notes?: string[] | null;
	focus?: string | null;
	variation_amplitude?: string | null;
	variation_seed?: number | null;
	interpret_fallback_used?: boolean;
	interpret_fallback_reasons?: string[];
	// Stage 2's counterpart. It exists only in the response, so a saved work
	// must carry it from here into persistence.
	compose_fallback_used?: boolean;
	compose_retry_reasons?: string[];
	tokens_in_stage1: number | null;
	tokens_out_stage1: number | null;
	tokens_in_stage2: number | null;
	tokens_out_stage2: number | null;
	user_generation_count?: number | null;
};

export type PaintOptions = {
	/** Plugin definitions from an imported DDL export, for a new work only. */
	importedPlugins?: ImportedPlugin[];
	historyInput?: string;
	saveHistory?: boolean;
	saveArtifacts?: boolean;
	countGeneration?: boolean;
	canvasAspectId?: CanvasAspectId;
	/** Fit a DDL that declares another ratio into the paper (DDL engine 70). */
	canvasFit?: 'contain';
	renderSeed?: Seed;
	/** Per-feature overrides for the render request; built by the features. */
	renderOverrides?: RenderOverrides;
	compositionSeed?: Seed;
	signal?: AbortSignal;
	sourceText?: string;
	displayLabel?: string;
	batchLineNumber?: number;
	batchRunId?: string;
	historyVisibility?: 'normal' | 'lineage_only';
	lineageParentNodeId?: string | null;
	derivationKind?: DerivationKind | null;
	derivationMetadata?: Record<string, unknown>;
	// Sketching runs only for an enabled mode. Stored prose is optional because
	// replay can reuse it instead of asking a non-deterministic layer again.
	sketchMode?: SketchMode;
	sketchText?: string | null;
	/** How the description is drawn; absent, the page's choice. */
	route?: DrawRoute;
	// Qualified model ids apply to this run only. Absence uses the page's
	// current model setting, which is what ordinary callers expect.
	stage1Model?: string;
	stage2Model?: string;
	// Runs after interpretation settles and before rendering starts.
	onStage1?: (event: PaintStage1Event) => void;
};

export type CurrentWorkDefaults = {
	uiLang: string;
	strings: LangPack;
	stage1Model: string;
	stage2Model: string;
	includeThinking: boolean;
	instructionLang: InstructionLang;
	canvasAspectId: CanvasAspectId;
	sketchMode: SketchMode;
	route: DrawRoute;
	renderPayload: Record<string, unknown>;
};

export type CurrentWorkCapabilities = {
	apiFetch: ApiFetch;
	describeApiError: (detail: unknown, status: number) => string;
	setStage1UserPrompt: (prompt: string) => void;
	setStageLabel: (label: string) => void;
	setActiveRunTokens: (tokensIn: number | null, tokensOut: number | null) => void;
	attachSavedLineage: () => void;
	updateGenerationCount: (count: number) => void;
	adoptPipelineView?: (view: PipelineView) => void;
	/** The model call being waited on; null once there is none. */
	setProviderAttempt?: (attempt: ProviderAttemptCount | null) => void;
};

export type CurrentWorkResult = { ddl: string; thinking: string | null } & PaintResult;

/**
 * Coordinate one paint-stream request and its immediate saved-work projection.
 *
 * The caller retains route state, outer loops, and AbortController ownership.
 * This function receives only resolved defaults and named capabilities, so one
 * run can be tested without constructing a Svelte route.
 */
export async function runCurrentWork(
	text: string,
	options: PaintOptions,
	defaults: CurrentWorkDefaults,
	capabilities: CurrentWorkCapabilities
): Promise<CurrentWorkResult> {
	capabilities.setActiveRunTokens(null, null);
	const historyInput = options.historyInput ?? text;
	// These are effective model ids, not raw form fields. The request, run
	// status, and saved work therefore name the same models.
	const resolvedStage1Model = options.stage1Model ?? defaults.stage1Model;
	const resolvedStage2Model = options.stage2Model ?? defaults.stage2Model;
	const resolvedSketchMode = options.sketchMode ?? defaults.sketchMode;
	const sketchOn = resolvedSketchMode !== 'off';
	const route = options.route ?? defaults.route;
	const readAndDraw = route === 'read_and_draw';

	capabilities.setStage1UserPrompt(text);
	// Before the first event, name the layer requested rather than guessing the
	// layer that will follow it.
	capabilities.setStageLabel(paintStageLabel('requested', defaults.strings, { sketchOn, readAndDraw }));

	let response: Response;
	try {
		response = await capabilities.apiFetch('/api/paint/stream', {
			method: 'POST',
			signal: options.signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({
				description: text,
				route,
				sketch: sketchOn,
				...(options.sketchText ? { sketch_text: options.sketchText } : {}),
				stage1_model: resolvedStage1Model,
				stage2_model: resolvedStage2Model,
				include_thinking: defaults.includeThinking,
				instruction_lang: defaults.instructionLang,
				ui_lang: defaults.uiLang,
				canvas_aspect: options.canvasAspectId ?? defaults.canvasAspectId,
				render_seed: options.renderSeed,
				composition_seed: options.compositionSeed,
				save_history: options.saveHistory ?? true,
				save_artifacts: options.saveArtifacts ?? true,
				count_generation: options.countGeneration ?? true,
				history_input: historyInput,
				history_source_text: options.sourceText ?? text,
				history_display_label: options.displayLabel ?? null,
				batch_line_number: options.batchLineNumber ?? null,
				batch_run_id: options.batchRunId ?? null,
				history_visibility: options.historyVisibility ?? 'normal',
				lineage_parent_node_id: options.lineageParentNodeId ?? null,
				derivation_kind: options.derivationKind ?? null,
				derivation_metadata: options.derivationMetadata ?? {},
				...defaults.renderPayload
			})
		});
	} catch (cause) {
		// A request that never reached the Server cut the connection, unless the caller stopped it.
		if (isAbort(cause, options.signal)) throw cause;
		throw new ConnectionFailure('unreachable', cause instanceof Error ? cause.message : String(cause), { cause });
	}
	if (!response.ok) {
		const data = await response.json().catch(() => ({})) as { detail?: unknown };
		const pipelineView = pipelineViewFromErrorDetail(data.detail);
		if (pipelineView) capabilities.adoptPipelineView?.(pipelineView);
		const message = capabilities.describeApiError(data.detail, response.status);
		// A gateway answering for a Server that is away carries no detail of the Server's own.
		if (GATEWAY_STATUSES.has(response.status) && data.detail === undefined) {
			throw new ConnectionFailure('gateway', message);
		}
		throw new Error(message);
	}

	let result: CurrentWorkResult;
	try {
		result = await readPaintStream<CurrentWorkResult>(response, {
			describeError: capabilities.describeApiError,
			onAttempt: (event) => capabilities.setProviderAttempt?.(event.provider_attempt),
			...paintStageHandlers(defaults.strings, capabilities.setStageLabel, {
				sketchOn,
				readAndDraw,
				onStage1: (event) => {
					capabilities.setActiveRunTokens(event.tokens_in, event.tokens_out);
					options.onStage1?.(event);
				}
			})
		});
	} finally {
		capabilities.setProviderAttempt?.(null);
	}

	capabilities.setActiveRunTokens(null, null);

	const unreadWords = interpretationFeedback(text, result.ddl)
		.filter((part) => part.tone === 'weak')
		.flatMap((part) => part.text.match(/[一-龯々ぁ-んァ-ヶー]{2,}|[A-Za-z][A-Za-z'-]+/g) ?? []);
	if (unreadWords.length > 0) {
		void capabilities.apiFetch('/api/feedback/unread-words', {
			method: 'POST',
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ words: unreadWords, context: text })
		}).catch(() => undefined);
	}

	if ((options.saveHistory ?? true) && result.lineage_node_id) {
		capabilities.attachSavedLineage();
	}
	if (typeof result.user_generation_count === 'number') {
		capabilities.updateGenerationCount(result.user_generation_count);
	}
	return result;
}
