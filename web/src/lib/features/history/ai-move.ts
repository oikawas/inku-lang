// The move an AI refinement child's lineage edge records (`ai_move`). The AI
// refinement (AI自動推敲) and its laws, juxtaposition and chunk moves were
// removed on 2026-11-13 (the author); the children it kept stay in the
// lineage, and their details still show the move each took.

export type AiMoveKind = 'laws' | 'juxtaposition' | 'chunks';

/** A share as the lineage's details print it, a whole percent. */
export function sharePercent(share: number | null | undefined): string | null {
	return typeof share === 'number' && Number.isFinite(share) ? String(Math.round(share * 100)) : null;
}

/** The page's words a chunk move is printed with. */
export type ChunkMoveWords = {
	aiRefineChunkMoveName: (move: string) => string;
	aiRefineChunkMove: (name: string, targets: string[], title: string | null) => string;
};

/** A chunk move as the lineage prints it: the move, the chunks it took and a redrawn chunk's new title. */
export function chunkMoveText(
	words: ChunkMoveWords, move: string | null | undefined, targets?: readonly string[] | null, title?: string | null
): string | null {
	if (!move) return null;
	return words.aiRefineChunkMove(words.aiRefineChunkMoveName(move), [...(targets ?? [])], title?.trim() || null);
}

/** The move a child's lineage edge records (`ai_move`), as the lineage's details show it. */
export type AiMoveRecord = {
	kind: AiMoveKind;
	turn: number | null;
	share: number | null;
	reason: string | null;
	mainLaw: string | null;
	sentence: string | null;
	move: string | null;
	targets: string[];
	title: string | null;
};

function fieldsOf(value: unknown): Record<string, unknown> {
	return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function textOf(value: unknown): string | null {
	return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/** Read field by field: an edge another build wrote may lack any of them; one with no known kind is no move. */
export function aiMoveOf(metadata: Record<string, unknown> | null | undefined): AiMoveRecord | null {
	const record = fieldsOf(metadata?.ai_move);
	const kind = record.kind;
	if (kind !== 'laws' && kind !== 'juxtaposition' && kind !== 'chunks') return null;
	const block = fieldsOf(record[kind]);
	const share = fieldsOf(record.visible).share;
	return {
		kind,
		turn: Number.isInteger(record.turn) ? record.turn as number : null,
		share: typeof share === 'number' && Number.isFinite(share) ? share : null,
		reason: textOf(block.reason),
		mainLaw: textOf(block.main_law),
		sentence: textOf(block.sentence),
		move: textOf(block.move),
		targets: Array.isArray(block.targets) ? block.targets.filter((title): title is string => typeof title === 'string') : [],
		title: textOf(block.title)
	};
}
