/** A system prompt as one work sent it, kept by the server on its execution. */
export type SentSystemPrompt = {
	system: string;
	prompt_id: string;
	prompt_digest: string;
	instruction_language: string;
	attempt: number;
	/** What the stage was given, kept for the sketch and the composition reading. */
	message?: string;
};

/** The stages whose prompts the tab shows, in the order a work calls them. */
export const PROMPT_STAGES = ['sketch', 'stage1', 'composition', 'stage2'] as const;
export type PromptStage = (typeof PROMPT_STAGES)[number];

/** The stages an execution saved before 2026-10-13 kept. */
const EARLIER_STAGES: PromptStage[] = ['stage1', 'stage2'];

/**
 * What the prompt tab can say about a work's system prompts.
 *
 * `recorded` carries each stage that called a model; a stage that did not is
 * null. `stages` names the stages the execution kept, so a stage outside it
 * was drawn before its record began. `not_recorded` is a work with no
 * shared-pipeline execution or one drawn before the record existed, and
 * `unavailable` a read that failed -- including someone else's work, whose
 * record only its owner may read.
 */
export type SystemPromptsState =
	| { state: 'loading' }
	| ({ state: 'recorded'; stages: PromptStage[] } & Record<PromptStage, SentSystemPrompt | null>)
	| { state: 'not_recorded' }
	| { state: 'unavailable' };

type Fetch = (path: string, init?: RequestInit) => Promise<Response>;

function sentPrompt(value: unknown): SentSystemPrompt | null {
	if (!value || typeof value !== 'object') return null;
	return typeof (value as { system?: unknown }).system === 'string' ? (value as SentSystemPrompt) : null;
}

export async function loadSystemPrompts(
	variationId: string | null | undefined,
	fetchRequest: Fetch = (path, init) => globalThis.fetch(path, init)
): Promise<SystemPromptsState> {
	if (!variationId) return { state: 'not_recorded' };
	try {
		const response = await fetchRequest(`/api/pipeline/variations/${encodeURIComponent(variationId)}/system-prompts`, {
			credentials: 'same-origin',
			cache: 'no-store'
		});
		if (!response.ok) return { state: 'unavailable' };
		const body = (await response.json()) as { recorded?: unknown; stages?: unknown } & Partial<Record<PromptStage, unknown>>;
		if (body?.recorded !== true) return { state: 'not_recorded' };
		// A server from before 2026-10-13 names no stages: it kept Stage 1 and Stage 2.
		const kept = Array.isArray(body.stages) ? body.stages : EARLIER_STAGES;
		return {
			state: 'recorded',
			stages: PROMPT_STAGES.filter((stage) => kept.includes(stage)),
			sketch: sentPrompt(body.sketch),
			stage1: sentPrompt(body.stage1),
			composition: sentPrompt(body.composition),
			stage2: sentPrompt(body.stage2)
		};
	} catch {
		return { state: 'unavailable' };
	}
}
