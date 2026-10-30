// The AI refinement's runs (AI自動推敲): the Server takes the moves on its own
// from a saved work, and the dialog starts a run, reads how it stands and stops
// it (the author, 2026-10-20: the run goes on with no screen open). A move is a
// laws move or a juxtaposition move, or a chunk move, which runs alone and
// needs the direction (2026-10-27); the shared core decides the tries, the
// visible-difference gate and the record a child keeps.

export type AutonomousKind = 'laws' | 'juxtaposition' | 'chunks';
export type AutonomousOutcome = 'kept' | 'not_visible' | 'unavailable' | 'failed';
export type AutonomousState = 'running' | 'done' | 'stopped' | 'failed' | 'interrupted';

export type AutonomousTry = {
	attempt: number;
	kind: AutonomousKind;
	outcome: AutonomousOutcome;
	reason?: string | null;
	/** The share of the drawn cells the child changed. */
	share?: number | null;
	main_law?: string | null;
	sentence?: string | null;
	rank?: number | null;
	/** The chunk move's move: omit, simplify, place, break, repeat or merge. */
	move?: string | null;
	/** The titles of the chunks a kept chunk move took. */
	targets?: string[] | null;
	/** The new title a simplify or a merge gave the chunk it redrew. */
	title?: string | null;
	history_id?: string | null;
	lineage_node_id?: string | null;
};

export type AutonomousRun = {
	id: string;
	history_id: string;
	state: AutonomousState;
	stop_reason?: string | null;
	stopping: boolean;
	settings: { moves: number; kinds: AutonomousKind[]; note?: string | null; model: string; language: string; wild?: boolean | null };
	turns: { attempts: AutonomousTry[] }[];
	current?: { turn: number; attempt: number; kind: AutonomousKind } | null;
	last_kept_history_id?: string | null;
	error?: string | null;
	created_at: number;
	updated_at: number;
};

/** What a run starts with; the page adds its language. */
export type AutonomousRunRequest = {
	history_id: string;
	moves: number;
	kinds: AutonomousKind[];
	note: string | null;
	model: string;
	/** null keeps each parent's Wild switch. */
	wild: boolean | null;
};

export type AutonomousRunsApi = {
	start: (request: AutonomousRunRequest) => Promise<AutonomousRun>;
	read: (runId: string, signal?: AbortSignal) => Promise<AutonomousRun>;
	stop: (runId: string) => Promise<AutonomousRun>;
	forHistory: (historyId: string, signal?: AbortSignal) => Promise<AutonomousRun[]>;
};

/** How often the dialog reads a running run. */
export const AUTONOMOUS_POLL_MS = 3000;
export const AUTONOMOUS_MOVES_DEFAULT = 5;
export const AUTONOMOUS_NOTE_LIMIT = 1000;

/** The run to show when a work is opened again: the one still going, if any. */
export function runToResume(runs: readonly AutonomousRun[]): AutonomousRun | null {
	return runs.find((run) => run.state === 'running') ?? null;
}

/** A share as the dialog prints it, a whole percent. */
export function sharePercent(share: number | null | undefined): string | null {
	return typeof share === 'number' && Number.isFinite(share) ? String(Math.round(share * 100)) : null;
}

/** The tries in the order they were taken, each with its turn. */
export function triesOf(run: AutonomousRun): { turn: number; attempt: AutonomousTry }[] {
	return run.turns.flatMap((turn, index) => turn.attempts.map((attempt) => ({ turn: index + 1, attempt })));
}

/** The kinds a run starts with: the chunk move runs alone (the Server refuses it beside the others). */
export function kindsOf(choice: { laws: boolean; juxtaposition: boolean; chunks: boolean }): AutonomousKind[] {
	if (choice.chunks) return ['chunks'];
	return [...(choice.laws ? ['laws' as const] : []), ...(choice.juxtaposition ? ['juxtaposition' as const] : [])];
}

/** The page's words a chunk move is printed with. */
export type ChunkMoveWords = {
	aiRefineChunkMoveName: (move: string) => string;
	aiRefineChunkMove: (name: string, targets: string[], title: string | null) => string;
};

/** A chunk move as the dialog and the lineage print it: the move, the chunks it took and a redrawn chunk's new title. */
export function chunkMoveText(
	words: ChunkMoveWords, move: string | null | undefined, targets?: readonly string[] | null, title?: string | null
): string | null {
	if (!move) return null;
	return words.aiRefineChunkMove(words.aiRefineChunkMoveName(move), [...(targets ?? [])], title?.trim() || null);
}

/** The move a child's lineage edge records (`ai_move`), as the lineage's details show it. */
export type AiMoveRecord = {
	kind: AutonomousKind;
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
