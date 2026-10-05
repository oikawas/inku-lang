import type { LangPack } from '../../i18n/types.ts';
import type { Seed } from '../run/current-work.ts';
import type { PaintResult } from '../run/current-work.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { PaintOptions } from '../run/current-work.ts';

export type RecomposeMode = 'principled' | 'chance';
export type Recomposition = {
	mode: RecomposeMode;
	outcome: 'recomposed' | 'unchanged';
	moves: Array<{ layer: number; from_key?: string | null; from: string; to_key: string; to: string }>;
	reason?: string | null;
	answer?: 'near' | 'next' | 'chance' | null;
};

export type LayoutParent = {
	id: string;
	ddl: string;
	catalogId: string | null;
	renderSeed: Seed | null;
	compositionSeed: Seed | null;
	canvasAspectId: string | null;
	stage1Model: string | null;
	instructionLang: string | null;
	ddlSourceOrigin: 'legacy_expanded' | null;
};

export type ComposeLayoutGeneration = (parent: LayoutParent, text: string, options: PaintOptions) => Promise<PaintResult & { ddl: string; thinking: string | null; source_text: string }>;

export type LayoutComposeResponse = Partial<PaintResult> & {
	ddl?: string;
	score: PaintResult['score'];
	svg: string;
	elapsed_ms?: number;
	tokens_in?: number | null;
	tokens_out?: number | null;
};

/** Both manual options and autonomous layout generations draw the saved DDL. */
export async function requestLayoutComposition(
	payload: Record<string, unknown>,
	mode: RecomposeMode,
	signal: AbortSignal | undefined,
	apiFetch: ApiFetch,
	apiError: (response: Response) => Promise<Error>
): Promise<LayoutComposeResponse> {
	const response = await apiFetch('/api/compose', {
		method: 'POST', signal, headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ ...payload, ...recompositionRequest(mode) })
	});
	if (!response.ok) throw await apiError(response);
	return await response.json() as LayoutComposeResponse;
}

export function layoutCandidateResult(data: LayoutComposeResponse, originalDdl: string, seed: Seed, mode: RecomposeMode) {
	return {
		...data,
		// Older compose responses do not carry DDL or recomposition metadata.
		ddl: data.ddl ?? originalDdl,
		composition_seed: data.composition_seed ?? seed,
		derivation_metadata: layoutDerivationMetadata(seed, mode)
	};
}

/** Omission keeps the old compose request unchanged. */
export function recompositionRequest(mode?: RecomposeMode): { recompose_mode?: RecomposeMode } {
	return mode ? { recompose_mode: mode } : {};
}

export function layoutDerivationMetadata(seed: Seed, mode: RecomposeMode): Record<string, unknown> {
	return { composition_seed: seed, recompose_mode: mode };
}

/** Core layer indexes are zero based; the author sees layers starting at one. */
export function recompositionLines(
	result: Recomposition | null | undefined,
	strings: Pick<LangPack, 'recomposeReason' | 'recomposeKeptRanges'>
): string[] {
	if (!result) return [];
	if (result.outcome === 'unchanged') return [strings.recomposeReason(result.reason), strings.recomposeKeptRanges];
	return result.moves.map((move) => `${move.layer + 1}: ${move.from} → ${move.to}`);
}
