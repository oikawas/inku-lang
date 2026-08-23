import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { SaveHistoryOptions } from '../history/save.ts';
import type { VariationCandidate } from './refinement-session.svelte.ts';

type CandidateResult = VariationCandidate['result'];

export type RefinementCandidateProjection = {
	ddl: string;
	expandedDdl: string;
	thinking: string | null;
	result: CandidateResult;
};

export type SaveRefinementCandidatesInput = {
	candidates: readonly VariationCandidate[];
	sourceText: () => string;
	fallbackCatalogId: () => string;
};

export type SaveRefinementCandidatesCapabilities = {
	saveHistory: (item: HistoryItem, options: SaveHistoryOptions) => Promise<HistoryItem | null>;
	isCurrentContext: () => boolean;
	markSaved: (id: string) => void;
	isCurrentResult: (result: CandidateResult) => boolean;
	adoptSavedIdentity: (result: CandidateResult, saved: HistoryItem) => void;
	now?: () => number;
};

export type SaveRefinementCandidatesOutcome = 'complete' | 'stale';

/** Map one generated candidate to the route's current-work projection. */
export function projectRefinementCandidate(
	candidate: VariationCandidate
): RefinementCandidateProjection {
	return {
		ddl: candidate.result.source_ddl ?? candidate.result.ddl,
		expandedDdl: candidate.result.ddl,
		thinking: candidate.result.thinking,
		result: candidate.result
	};
}

/** Persist a selected snapshot without acquiring route or session state. */
export async function saveRefinementCandidates(
	input: SaveRefinementCandidatesInput,
	capabilities: SaveRefinementCandidatesCapabilities
): Promise<SaveRefinementCandidatesOutcome> {
	const now = capabilities.now ?? Date.now;
	// Saving stays sequential so generation counts and history refreshes retain
	// the same order as the candidate cards supplied by the session.
	for (const candidate of input.candidates) {
		const result = candidate.result;
		const sourceText = input.sourceText();
		const saved = await capabilities.saveHistory({
			...result,
			input: sourceText,
			ddl: result.ddl,
			score: result.score,
			svg: result.svg,
			at: now(),
			elapsed_ms: result.elapsed_total_ms ?? 0,
			stage1_model: result.stage1_model ?? null,
			stage2_model: result.stage2_model ?? null,
			tokens_in: (result.tokens_in_stage1 ?? 0) + (result.tokens_in_stage2 ?? 0) || null,
			tokens_out: (result.tokens_out_stage1 ?? 0) + (result.tokens_out_stage2 ?? 0) || null,
			catalog_id: result.render_color_catalog_id ?? input.fallbackCatalogId()
		}, {
			countGeneration: true,
			sourceText,
			lineageParentNodeId: result.lineage_parent_node_id ?? null,
			derivationKind: result.derivation_kind ?? null,
			derivationMetadata: result.derivation_metadata ?? {}
		});
		// The save may finish after the author has switched targets. Check before
		// changing selection or starting the next write.
		if (!capabilities.isCurrentContext()) return 'stale';
		capabilities.markSaved(candidate.id);
		// A saved id belongs on the Canvas only when it is still showing this exact
		// result object; another candidate must not inherit the persisted identity.
		if (saved?.id && capabilities.isCurrentResult(result)) {
			capabilities.adoptSavedIdentity(result, saved);
		}
	}
	return 'complete';
}
