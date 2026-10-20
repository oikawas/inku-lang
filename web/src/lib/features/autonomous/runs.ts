// The AI refinement's runs (AI自動推敲): the Server takes the moves on its own
// from a saved work, and the dialog starts a run, reads how it stands and stops
// it (the author, 2026-10-20: the run goes on with no screen open). A move is a
// laws move or a juxtaposition move; the shared core decides the tries, the
// visible-difference gate and the record a child keeps.

export type AutonomousKind = 'laws' | 'juxtaposition';
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
