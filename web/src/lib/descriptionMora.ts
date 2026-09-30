/**
 * Asking the Server for a description's sounds (POST /api/description/mora).
 *
 * The description meter is one component shown in two places, neither of
 * which is handed the page's transport, so the page registers it here once.
 * Answers are kept for the texts last asked about: the box and the dialog
 * often show the same description, and a keystroke undone asks again.
 */

import type { MoraCount } from './verseForm';

type Fetcher = (path: string, init?: RequestInit) => Promise<Response>;

let transport: Fetcher | null = null;
const answers = new Map<string, MoraCount>();
const KEPT_ANSWERS = 32;
/** The Server counts at most this much; a longer description is counted by characters. */
export const MORA_TEXT_LIMIT = 4000;

export function registerMoraTransport(fetcher: Fetcher): void {
	transport = fetcher;
}

/** The sounds of `text`, or null when there is no transport or the Server does not answer. */
export async function fetchMora(text: string, signal?: AbortSignal): Promise<MoraCount | null> {
	const kept = answers.get(text);
	if (kept) return kept;
	if (!transport || text.length > MORA_TEXT_LIMIT) return null;
	const response = await transport('/api/description/mora', {
		method: 'POST',
		signal,
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify({ text })
	});
	if (!response.ok) return null;
	const counted = await response.json() as MoraCount;
	answers.set(text, counted);
	if (answers.size > KEPT_ANSWERS) answers.delete(answers.keys().next().value as string);
	return counted;
}
