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
