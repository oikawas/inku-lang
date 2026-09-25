/** A system prompt as one work sent it, kept by the server on its execution. */
export type SentSystemPrompt = {
	system: string;
	prompt_id: string;
	prompt_digest: string;
	instruction_language: string;
	attempt: number;
};

/**
 * What the prompt tab can say about a work's system prompts.
 *
 * `recorded` carries each stage that called a model; a stage that did not is
 * null. `not_recorded` is a work with no shared-pipeline execution or one drawn
 * before the record existed, and `unavailable` a read that failed -- including
 * someone else's work, whose record only its owner may read.
 */
export type SystemPromptsState =
	| { state: 'loading' }
	| { state: 'recorded'; stage1: SentSystemPrompt | null; stage2: SentSystemPrompt | null }
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
		const body = (await response.json()) as { recorded?: unknown; stage1?: unknown; stage2?: unknown };
		if (body?.recorded !== true) return { state: 'not_recorded' };
		return { state: 'recorded', stage1: sentPrompt(body.stage1), stage2: sentPrompt(body.stage2) };
	} catch {
		return { state: 'unavailable' };
	}
}
