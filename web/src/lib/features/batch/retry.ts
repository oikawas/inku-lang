// The decision of what to redraw after a batch finishes, kept apart from the
// drawing itself. paintOne() calls a model, so a test that drove the retry loop
// end to end would need an LLM; the rules that actually matter -- stop at the
// limit, stop when the run was interrupted, drop lines that have since
// succeeded -- are arithmetic over a list and are testable on their own.

// Structurally the same shape as BatchFailure in failure-report.svelte.ts, and
// deliberately not imported from it: that module declares $state, so pulling it
// in here would drag the Svelte compiler into a plain node:test run.
export type BatchFailure = {
	line: number;
	input: string;
	message: string;
};

export type RetryRound = {
	/** 1-based: the first retry pass is round 1, the original pass is not a round. */
	round: number;
	items: BatchFailure[];
};

/**
 * The next retry round, or null when the batch is done.
 *
 * `completedRounds` counts retry rounds already run, not the original pass.
 * `interrupted` is the stop button or an aborted request: an interrupted batch
 * is never retried, because the lines that did not run are not failures.
 */
export function planRetryRound(
	failures: readonly BatchFailure[],
	completedRounds: number,
	maxRetries: number,
	interrupted: boolean,
): RetryRound | null {
	if (interrupted) return null;
	if (failures.length === 0) return null;
	const hasRoundsLeft = completedRounds < maxRetries;
	if (!hasRoundsLeft) return null;
	return { round: completedRounds + 1, items: [...failures] };
}

/** The failure list with one line removed, for a line that succeeded on retry. */
export function dropFailedLine(
	failures: readonly BatchFailure[],
	line: number,
): BatchFailure[] {
	return failures.filter((failure) => failure.line !== line);
}
