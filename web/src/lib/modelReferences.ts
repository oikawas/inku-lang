import { SvelteMap } from 'svelte/reactivity';

export type ReferenceQuery = { action: 'split_ref' | 'qualify_ref' | 'resolve_ref' | 'resolve_display'; ref: string; provider?: string; default_provider?: string };
export type ReferenceResult = { outcome: string; ref?: string; provider?: string | null; model?: string; provider_label?: string; provider_abbreviation?: string; model_label?: string; display_name?: string; strip_label?: string };
type Transport = (path: string, init?: RequestInit) => Promise<Response>;
const answers = new SvelteMap<string, ReferenceResult>();
const waiting = new Map<string, ReferenceQuery>();
let transport: Transport | undefined;
// The core names a sign-in service ("Sign in with ChatGPT") in the screen's language, so an
// answer is kept per language and the request says which one.
let language: () => string = () => 'en';
let scheduled = false;
let generation = 0;
const keyOf = (query: ReferenceQuery, lang = language()) => JSON.stringify([query.action, query.ref, query.provider ?? '', query.default_provider ?? '', lang]);

export function configureModelReferences(fetcher: Transport, lang?: () => string): void {
	transport = fetcher;
	if (lang) language = lang;
}
export function clearModelReferences(): void { generation++; answers.clear(); waiting.clear(); }
export function disableModelReferences(): void { clearModelReferences(); transport = undefined; }
export function clearChatGPTReferences(): void {
	generation++;
	for (const [key, answer] of answers) {
		const [, ref, provider] = JSON.parse(key) as string[];
		if (ref.startsWith('chatgpt:') || provider === 'chatgpt' || answer.provider === 'chatgpt') answers.delete(key);
	}
	for (const [key, query] of waiting) {
		if (query.ref.startsWith('chatgpt:') || query.provider === 'chatgpt') waiting.delete(key);
	}
}

async function requestBatch(queries: ReferenceQuery[], version: number): Promise<void> {
	if (!transport) throw new Error('model reference transport unavailable');
	const lang = language() === 'ja' ? 'ja' : 'en';
	for (let index = 0; index < queries.length; index += 256) {
		const batch = queries.slice(index, index + 256);
		const response = await transport('/api/model-references', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ queries: batch, language: lang }) });
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		const data = await response.json() as { results: ReferenceResult[] };
		if (!Array.isArray(data.results) || data.results.length !== batch.length || data.results.some((result) => result.outcome !== 'ok')) throw new Error('invalid model reference response');
		if (version !== generation) return;
		for (let i = 0; i < batch.length; i++) answers.set(keyOf(batch[i], language()), data.results[i]);
	}
}

// Replace a refresh's answers only after every new answer has arrived, keeping
// the displayed names intact during network requests.
export async function refreshModelReferences(queries: ReferenceQuery[], current: () => boolean): Promise<void> {
 if (!transport) throw new Error('model reference transport unavailable');
 const version = generation;
 const lang = language() === 'ja' ? 'ja' : 'en';
 const unique = new Map(queries.map(query => [keyOf(query, lang), query]));
 for (const key of answers.keys()) {
  const [action, ref, provider, default_provider, answerLang] = JSON.parse(key) as string[];
  if (action === 'resolve_display' && answerLang === lang) unique.set(key, {action: 'resolve_display', ref, provider: provider || undefined, default_provider: default_provider || undefined});
 }
 const all = [...unique.values()];
 const next = new Map<string, ReferenceResult>();
 for (let index = 0; index < all.length; index += 256) {
  const batch = all.slice(index, index + 256);
  const response = await transport('/api/model-references', {method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({queries: batch, language: lang})});
  if (!response.ok) throw new Error(`HTTP ${response.status}`);
  const data = await response.json() as {results: ReferenceResult[]};
  if (!Array.isArray(data.results) || data.results.length !== batch.length || data.results.some(result => result.outcome !== 'ok')) throw new Error('invalid model reference response');
  batch.forEach((query, i) => next.set(keyOf(query, lang), data.results[i]));
 }
 if (version !== generation || !current()) return;
 for (const [key, value] of next) answers.set(key, value);
}

export async function loadModelReferences(queries: ReferenceQuery[]): Promise<void> {
	const unique = new Map(queries.map((query) => [keyOf(query), query]));
	let version: number;
	do {
		version = generation;
		await requestBatch([...unique.values()].filter((query) => !answers.has(keyOf(query))), version);
	} while (version !== generation);
}

export function modelReference(query: ReferenceQuery): ReferenceResult | undefined {
	const key = keyOf(query);
	const result = answers.get(key);
	if (result || !transport) return result;
	waiting.set(key, query);
	if (!scheduled) {
		scheduled = true;
		queueMicrotask(() => {
			scheduled = false;
			const batch = [...waiting.values()]; waiting.clear();
			void requestBatch(batch, generation).catch(() => {});
		});
	}
	return undefined;
}
