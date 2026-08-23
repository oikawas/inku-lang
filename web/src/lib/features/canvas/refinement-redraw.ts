import type { CanvasAspectId } from '../../plugins/system/canvas-aspect/index.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { RenderOverrides } from '../render-payload.ts';
import type {
	CurrentWorkResult,
	PaintOptions,
	PaintResult
} from '../run/current-work.ts';

export type TouchRedrawInput = {
	current: PaintResult;
	canvasAspectId: CanvasAspectId;
	parentNodeId: string | null;
	workReference: Record<string, string>;
	renderPayload: Record<string, unknown>;
};

export type TouchRedrawCapabilities = {
	apiFetch: ApiFetch;
	apiError(response: Response): Promise<Error>;
	createRenderSeed(excluded: Set<number>): number;
	currentResult(): PaintResult;
};

type PaintRedrawInput = {
	source: string;
	canvasAspectId: CanvasAspectId;
	renderOverrides: RenderOverrides;
	parentNodeId: string | null;
};

export type LayoutRedrawInput = PaintRedrawInput & {
	current: PaintResult;
};

export type LayoutRedrawCapabilities = {
	createCompositionSeed(excluded: Set<number>): number;
	paint(source: string, options: PaintOptions): Promise<CurrentWorkResult>;
};

export type ReadingRedrawCapabilities = {
	createInterpretationSeed(): string;
	paint(source: string, options: PaintOptions): Promise<CurrentWorkResult>;
};

export type RefinementRedrawProjection = {
	ddl: string;
	expandedDdl: string;
	thinking: string | null;
	result: CurrentWorkResult;
	elapsedStage1Ms: number;
	elapsedStage2Ms: number;
	elapsedTotalMs: number;
	tokensInStage1: number | null;
	tokensOutStage1: number | null;
	tokensInStage2: number | null;
	tokensOutStage2: number | null;
};

/**
 * Redraw only the touch while retaining the effective placement seed.
 *
 * The renderer places a work with composition_seed when present and otherwise
 * uses render_seed. Nullish fallback is required because seed zero is valid.
 */
export async function runTouchRedraw(
	input: TouchRedrawInput,
	capabilities: TouchRedrawCapabilities
): Promise<PaintResult> {
	const usedSeeds = new Set<number>();
	if (Number.isFinite(input.current.render_seed ?? NaN)) {
		usedSeeds.add(Number(input.current.render_seed));
	}
	const nextSeed = capabilities.createRenderSeed(usedSeeds);
	const placementSeed = input.current.composition_seed ?? input.current.render_seed ?? null;
	const response = await capabilities.apiFetch('/api/render-svg', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({
			score: input.current.score,
			canvas_aspect: input.canvasAspectId,
			render_seed: nextSeed,
			composition_seed: placementSeed,
			// Saved-work colors remain canonical; the catalog payload is its nameplate.
			...input.workReference,
			...input.renderPayload
		})
	});
	if (!response.ok) throw await capabilities.apiError(response);
	const svg = await response.text();
	// The route historically resolves the base again after the request. Keep that
	// timing explicit here; changing stale-target behavior belongs to its own repair.
	const current = capabilities.currentResult();
	return {
		...current,
		svg,
		render_seed: nextSeed,
		composition_seed: placementSeed,
		render_hash: null,
		render_hash_short: null,
		history_id: null,
		history_at: null,
		lineage_node_id: null,
		lineage_parent_node_id: input.parentNodeId,
		derivation_kind: input.parentNodeId ? 'touch_change' : null,
		derivation_metadata: {
			render_seed_from: current.render_seed ?? null,
			render_seed_to: nextSeed
		}
	};
}

export async function runLayoutRedraw(
	input: LayoutRedrawInput,
	capabilities: LayoutRedrawCapabilities
): Promise<CurrentWorkResult> {
	const usedSeeds = new Set<number>();
	if (Number.isFinite(input.current.composition_seed ?? NaN)) {
		usedSeeds.add(Number(input.current.composition_seed));
	}
	const compositionSeed = capabilities.createCompositionSeed(usedSeeds);
	return capabilities.paint(input.source, {
		compositionSeed,
		historyInput: input.source,
		sourceText: input.source,
		canvasAspectId: input.canvasAspectId,
		renderOverrides: input.renderOverrides,
		lineageParentNodeId: input.parentNodeId,
		derivationKind: input.parentNodeId ? 'layout_change' : null,
		derivationMetadata: { composition_seed: compositionSeed }
	});
}

export async function runReadingRedraw(
	input: PaintRedrawInput,
	capabilities: ReadingRedrawCapabilities
): Promise<CurrentWorkResult> {
	const interpretationSeed = capabilities.createInterpretationSeed();
	return capabilities.paint(input.source, {
		historyInput: input.source,
		sourceText: input.source,
		canvasAspectId: input.canvasAspectId,
		renderOverrides: input.renderOverrides,
		interpretationSeed,
		lineageParentNodeId: input.parentNodeId,
		derivationKind: input.parentNodeId ? 'reinterpretation' : null,
		derivationMetadata: { interpretation_seed: interpretationSeed }
	});
}

/** Map a Paint result to the route fields updated by layout and reading redraws. */
export function projectRefinementRedrawResult(
	result: CurrentWorkResult
): RefinementRedrawProjection {
	return {
		ddl: result.source_ddl ?? result.ddl,
		expandedDdl: result.ddl,
		thinking: result.thinking,
		result,
		elapsedStage1Ms: result.elapsed_stage1_ms,
		elapsedStage2Ms: result.elapsed_stage2_ms,
		elapsedTotalMs: result.elapsed_total_ms,
		tokensInStage1: result.tokens_in_stage1,
		tokensOutStage1: result.tokens_out_stage1,
		tokensInStage2: result.tokens_in_stage2,
		tokensOutStage2: result.tokens_out_stage2
	};
}
