import type { LangPack } from '../../i18n/types';
import type { PipelineView } from './api';

export type HoleCompletionIssue = { holeId: string; source: string; reason: string };

/** Explain uncompleted holes when the author must decide or edit. */
export function holeCompletionIssues(
	view: Pick<PipelineView, 'phase' | 'hole_completion_check'> | null | undefined,
	strings: LangPack,
): HoleCompletionIssue[] {
	if (!view) return [];
	const phase = view.phase;
	const stopped = (phase.tag === 'needs_user_edit' || phase.tag === 'failed')
		&& (phase.reason === 'hole_completion_failed' || phase.reason === 'hole_completion_context_limit');
	if (phase.tag !== 'awaiting_patch_approval' && !stopped) return [];
	return (view.hole_completion_check?.results ?? [])
		.filter(result => result.status === 'rejected' || result.status === 'unresolved')
		.map(result => ({
			holeId: result.hole_id,
			source: typeof result.source === 'string' ? result.source : '',
			reason: strings.pipelineCompletionReason(result.reason ?? 'unknown'),
		}));
}
