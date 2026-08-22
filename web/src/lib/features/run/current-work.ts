import type { DerivationKind } from '../../derivation.ts';
import { interpretationFeedback } from '../../highlight.ts';
import type { LangPack } from '../../i18n/types.ts';
import {
	paintStageHandlers,
	paintStageLabel,
	readPaintStream,
	type PaintStage1Event
} from '../../paintStream.ts';
import type { CanvasAspectId } from '../../plugins/system/canvas-aspect/index.ts';
import { sketchGrainOf, type SketchMode } from '../../sketch.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { RenderOverrides } from '../render-payload.ts';

export type InstructionLang = 'auto' | 'ja' | 'en';

export type PaintScore = {
	instructions: unknown[];
	canvas?: string | null;
};

export type PaintResult = {
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
	render_seed?: number | null;
	render_wild?: boolean | null;
	composition_seed?: number | null;
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
	source_ddl?: string | null;
	// What the expansion layer removed and why. This reaches the record on
	// every path, so the author can see which part of the sentence was lost.
	plugin_warnings?: string[] | null;
	// Which render limits took effect and where they came from. The values say
	// what was used; the source distinguishes a replayed ceiling (ledger I-154).
	render_limits?: Record<string, number> | null;
	render_limits_source?: string | null;
	render_limit_notes?: string[] | null;
	focus?: string | null;
	variation_amplitude?: string | null;
	variation_seed?: number | null;
	variation_moved_axes?: Array<{ axis: string; from: string; to: string }>;
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
	historyInput?: string;
	saveHistory?: boolean;
	saveArtifacts?: boolean;
	countGeneration?: boolean;
	canvasAspectId?: CanvasAspectId;
	renderSeed?: number;
	/** Per-feature overrides for the render request; built by the features. */
	renderOverrides?: RenderOverrides;
	compositionSeed?: number;
	// Variation shifts the expansion layer only when both values exist.
	variationAmplitude?: string;
	variationSeed?: number;
	interpretationSeed?: string;
	seedText?: string;
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
	ddlAutoRepairEnabled: boolean;
	sketchMode: SketchMode;
	renderPayload: Record<string, unknown>;
};

export type CurrentWorkCapabilities = {
	apiFetch: ApiFetch;
	describeApiError: (detail: unknown, status: number) => string;
	setStage1UserPrompt: (prompt: string) => void;
	setStageLabel: (label: string) => void;
	setActiveRunTokens: (tokensIn: number | null, tokensOut: number | null) => void;
	loadNearbyHistory: (historyId: string | null | undefined) => Promise<void>;
	attachSavedLineage: () => void;
	updateGenerationCount: (count: number) => void;
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
	const resolvedSketchGrain = sketchGrainOf(resolvedSketchMode);
	const sketchOn = resolvedSketchMode !== 'off';

	capabilities.setStage1UserPrompt(text);
	// Before the first event, name the layer requested rather than guessing the
	// layer that will follow it.
	capabilities.setStageLabel(paintStageLabel('requested', defaults.strings, { sketchOn }));

	const response = await capabilities.apiFetch('/api/paint/stream', {
		method: 'POST',
		signal: options.signal,
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			description: text,
			sketch: sketchOn,
			...(resolvedSketchGrain ? { sketch_grain: resolvedSketchGrain } : {}),
			...(options.sketchText ? { sketch_text: options.sketchText } : {}),
			stage1_model: resolvedStage1Model,
			stage2_model: resolvedStage2Model,
			include_thinking: defaults.includeThinking,
			instruction_lang: defaults.instructionLang,
			ui_lang: defaults.uiLang,
			canvas_aspect: options.canvasAspectId ?? defaults.canvasAspectId,
			render_seed: options.renderSeed,
			composition_seed: options.compositionSeed,
			variation_amplitude: options.variationAmplitude ?? null,
			variation_seed: options.variationSeed ?? null,
			interpretation_seed: options.interpretationSeed,
			seed_text: options.seedText,
			auto_repair: defaults.ddlAutoRepairEnabled,
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
	if (!response.ok) {
		const data = await response.json().catch(() => ({})) as { detail?: unknown };
		throw new Error(capabilities.describeApiError(data.detail, response.status));
	}

	const result = await readPaintStream<CurrentWorkResult>(response, {
		describeError: capabilities.describeApiError,
		...paintStageHandlers(defaults.strings, capabilities.setStageLabel, {
			sketchOn,
			onStage1: (event) => {
				capabilities.setActiveRunTokens(event.tokens_in, event.tokens_out);
				options.onStage1?.(event);
			}
		})
	});

	capabilities.setActiveRunTokens(null, null);
	await capabilities.loadNearbyHistory(result.history_id);

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
