/**
 * The tokens a work's sends used, as the generation information shows them:
 * the total alone, or with a row for each stage that sent (2026-10-26). Which
 * one is the account's choice, stored in `model_settings` beside the drawer's
 * follow choice (./generation-info-follow.ts).
 *
 * Plain .ts (no runes), so the parsing and the rows are testable without the
 * compiler.
 */

/** Key as the server stores it inside `model_settings`. */
export const TOKEN_DETAIL_FIELD = 'generation_info_token_detail';

/** The total alone for an account that never chose: it is how the row read before. */
export const TOKEN_DETAIL_DEFAULT = false;

export function tokenDetailFromSettings(settings: Record<string, unknown> | null | undefined): boolean {
	const stored = settings?.[TOKEN_DETAIL_FIELD];
	return typeof stored === 'boolean' ? stored : TOKEN_DETAIL_DEFAULT;
}

/** One stage's sends, as the server saves them with the work (`provider_usage`). */
export type ProviderStageUsage = {
	sends: number;
	unreported_sends: number;
	input_tokens: number | null;
	output_tokens: number | null;
	cached_input_tokens: number | null;
};

export type ProviderUsage = Record<string, ProviderStageUsage>;

/** The stages in the order a work calls them, by the name the server times them under. */
export const TOKEN_STAGES = ['read_and_draw', 'image', 'stage1', 'composition', 'laws', 'colors', 'stage2'] as const;

export type TokenStage = (typeof TOKEN_STAGES)[number];

/** The message that names each stage's row; a stage the server adds later shows its own name. */
export const TOKEN_STAGE_LABELS = {
	read_and_draw: 'provenanceTokenStageReadAndDraw',
	image: 'provenanceTokenStagePicture',
	stage1: 'provenanceTokenStageStage1',
	composition: 'provenanceTokenStageComposition',
	laws: 'provenanceTokenStageLaws',
	colors: 'provenanceTokenStageColors',
	stage2: 'provenanceTokenStageStage2'
} as const satisfies Record<TokenStage, string>;

export function tokenStageLabel(stage: string, messages: Record<(typeof TOKEN_STAGE_LABELS)[TokenStage], string>): string {
	return stage in TOKEN_STAGE_LABELS ? messages[TOKEN_STAGE_LABELS[stage as TokenStage]] : stage;
}

export type TokenStageRow = { stage: string; usage: ProviderStageUsage };

/** The rows of the stages that sent, known stages first in call order, then any other. */
export function tokenStageRows(record: ProviderUsage | null | undefined): TokenStageRow[] {
	if (!record) return [];
	const known: readonly string[] = TOKEN_STAGES;
	const names = [
		...TOKEN_STAGES.filter((stage) => record[stage]),
		...Object.keys(record).filter((stage) => !known.includes(stage)).sort()
	];
	return names.filter((stage) => record[stage]?.sends > 0).map((stage) => ({ stage, usage: record[stage] }));
}
