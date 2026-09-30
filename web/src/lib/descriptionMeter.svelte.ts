/**
 * What the description meter needs from the Server: the counts
 * (POST /api/description/mora for Japanese sounds, /api/description/syllables
 * for English syllables) and whether each language is judged at all
 * (Settings > Other (server), read from /api/client-config).
 *
 * The meter is one component shown in two places, neither of which is handed
 * the page's transport, so the page registers it here once. Answers are kept
 * for the texts last asked about: the box and the dialog often show the same
 * description, and a keystroke undone asks again.
 */

import type { MeterSwitches, MoraCount, SyllableCount } from './verseForm';

type Fetcher = (path: string, init?: RequestInit) => Promise<Response>;

let transport: Fetcher | null = null;
const KEPT_ANSWERS = 32;
/** The Server counts at most this much; a longer description is judged on the page. */
export const METER_TEXT_LIMIT = 4000;

/** Both languages are judged until the Server says otherwise. */
export const meterSwitches = $state<MeterSwitches>({ japanese: true, english: true });

export function registerMeterTransport(fetcher: Fetcher): void {
	transport = fetcher;
}

export function applyMeterSwitches(value: unknown): void {
	if (!value || typeof value !== 'object') return;
	const switches = value as Partial<MeterSwitches>;
	if (typeof switches.japanese === 'boolean') meterSwitches.japanese = switches.japanese;
	if (typeof switches.english === 'boolean') meterSwitches.english = switches.english;
}

function keptAsker<T>(path: string) {
	const answers = new Map<string, T>();
	return async (text: string, signal?: AbortSignal): Promise<T | null> => {
		const kept = answers.get(text);
		if (kept) return kept;
		if (!transport || text.length > METER_TEXT_LIMIT) return null;
		const response = await transport(path, {
			method: 'POST',
			signal,
			headers: { 'Content-Type': 'application/json' },
			body: JSON.stringify({ text })
		});
		if (!response.ok) return null;
		const counted = await response.json() as T;
		answers.set(text, counted);
		if (answers.size > KEPT_ANSWERS) answers.delete(answers.keys().next().value as string);
		return counted;
	};
}

/** The sounds of a Japanese description, or null when the Server does not answer. */
export const fetchMora = keptAsker<MoraCount>('/api/description/mora');
/** The syllables of an English description, line by line, or null when the Server does not answer. */
export const fetchSyllables = keptAsker<SyllableCount>('/api/description/syllables');
