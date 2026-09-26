import type { LangPack } from '$lib/i18n/types';
import { pipelineAttentionText, type PipelineProviderFailure } from './features/pipeline/attention';

type ProviderFailure = {
	code: 'model_gone' | 'provider_auth' | 'provider_rate_limit' | 'provider_error';
	stage: string;
	provider_status: number;
	message: string;
};

type JsonObject = Record<string, unknown>;

const SCORE_INVALID = 'score is invalid: ';
const SCORE_NOT_RENDERABLE = 'score cannot be rendered: ';

function object(value: unknown): JsonObject | null {
	return value !== null && typeof value === 'object' && !Array.isArray(value)
		? value as JsonObject
		: null;
}

function providerFailure(value: unknown): ProviderFailure | null {
	const failure = object(value);
	if (!failure) return null;
	if (
		failure.code !== 'model_gone'
		&& failure.code !== 'provider_auth'
		&& failure.code !== 'provider_rate_limit'
		&& failure.code !== 'provider_error'
	) return null;
	if (
		typeof failure.stage !== 'string'
		|| typeof failure.provider_status !== 'number'
		|| typeof failure.message !== 'string'
	) return null;
	return failure as ProviderFailure;
}

function pipelineActionMessage(detail: JsonObject, strings: LangPack): string | null {
	if (
		detail.code !== 'pipeline_author_action_required'
		&& detail.code !== 'pipeline_patch_approval_required'
	) return null;
	const view = object(detail.current_view);
	const phase = object(view?.phase);
	if (typeof phase?.reason === 'string' && phase.reason) {
		return pipelineAttentionText(phase.reason, object(view?.provider_failure) as PipelineProviderFailure | null, strings);
	}
	if (phase?.tag === 'awaiting_patch_approval' || detail.code === 'pipeline_patch_approval_required') {
		return strings.pipelinePatchHint;
	}
	return typeof detail.message === 'string' && detail.message
		? detail.message
		: strings.pipelineRequestFailed;
}

/** Turn a Server failure detail into one human-readable line. */
export function describeApiErrorDetail(detail: unknown, status: number, strings: LangPack): string {
	if (detail === 'render capacity is full') return strings.errorRenderBusy;
	if (detail === 'description is only labels') return strings.errorDescriptionOnlyLabels;
	// The account deletions the server refuses, said in the page's language.
	if (detail === 'user has history') return strings.errorUserHasWorks;
	if (detail === "other accounts' works derive from this user's works") return strings.errorUserIsLineageOrigin;
	if (detail === 'the last administrator cannot be removed') return strings.errorLastAdministrator;
	// A model the administrator has not offered: a string from the routes that
	// call one directly, a code from the authoring pipeline.
	if (detail === 'model is not offered on this server') return strings.errorModelNotOffered;
	// A Score the server will not take or the render core will not draw: the
	// headline in the page's language, the reason as the validator or the core
	// wrote it.
	if (typeof detail === 'string' && detail.startsWith(SCORE_INVALID)) {
		return strings.errorScoreInvalid(detail.slice(SCORE_INVALID.length));
	}
	if (typeof detail === 'string' && detail.startsWith(SCORE_NOT_RENDERABLE)) {
		return strings.errorScoreNotRenderable(detail.slice(SCORE_NOT_RENDERABLE.length));
	}
	if (typeof detail === 'string' && detail) return detail;

	const structured = object(detail);
	if (structured?.code === 'model_not_offered') return strings.errorModelNotOffered;
	if (structured) {
		const pipelineMessage = pipelineActionMessage(structured, strings);
		if (pipelineMessage) return pipelineMessage;
	}

	const failure = providerFailure(detail);
	if (failure) {
		const stage = failure.stage === 'interpret' ? strings.runStatusStage1 : strings.runStatusStage2;
		const headline =
			failure.code === 'model_gone'
				? strings.errorModelGone(stage)
				: failure.code === 'provider_auth'
					? strings.errorProviderAuth(stage)
					: failure.code === 'provider_rate_limit'
						? strings.errorProviderRateLimit(stage)
						: strings.errorProviderOther(stage, failure.provider_status);
		return `${headline}\n${failure.message}`;
	}

	if (typeof structured?.message === 'string' && structured.message) return structured.message;
	return `HTTP ${status}`;
}
