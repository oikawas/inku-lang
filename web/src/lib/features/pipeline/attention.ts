// The line that tells the author a run stopped and why.
//
// The phase names the stage that failed; the model's own failure, which the
// running view keeps as `provider_failure`, says what happened to it. A run
// whose every Stage 1 attempt timed out used to end with only "the
// description could not be interpreted".
import type { LangPack } from '../../i18n/types';

/** The stage a failed phase belongs to, as `provider_failure.stage` names it. */
const STAGE_OF_REASON: Record<string, string> = {
	stage1_failed: 'stage1',
	hole_completion_failed: 'stage2',
};

/**
 * The reason to show the author, or null while the run is still going.
 *
 * Three phases carry a reason, and only two of them have stopped: the run
 * needs the author's edit, or it failed. The third, a Stage 1 result waiting
 * to be saved, carries the commit's reason (`stage1_generated`) and moves on
 * by itself; reading it as a stop put "check the result" on screen for the
 * moment every drawing was being saved.
 */
const STOPPED_PHASES = new Set(['needs_user_edit', 'failed']);

export function pipelineAttentionReason(phase: { tag?: unknown; reason?: unknown } | null | undefined): string | null {
	if (!phase || typeof phase.tag !== 'string' || !STOPPED_PHASES.has(phase.tag)) return null;
	return typeof phase.reason === 'string' && phase.reason ? phase.reason : null;
}

export type PipelineProviderFailure = {
	failure?: unknown;
	stage?: unknown;
	attempt?: unknown;
	detail?: unknown;
};

export function pipelineAttentionText(
	reason: string,
	failure: PipelineProviderFailure | null | undefined,
	strings: LangPack
): string {
	const base = `${strings.pipelineNeedsAttention} ${strings.pipelineAttentionReason(reason)}`;
	// Only a failure of the stage that stopped explains it; an earlier stage's
	// retry that later succeeded does not.
	if (!failure || typeof failure.failure !== 'string' || failure.stage !== STAGE_OF_REASON[reason]) return base;
	const attempts = typeof failure.attempt === 'number' ? failure.attempt : 1;
	const detail = typeof failure.detail === 'string' ? failure.detail : null;
	return base + strings.pipelineFailureCause(failure.failure, attempts, detail);
}
