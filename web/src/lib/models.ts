export type Provider = string;

export type ModelOption = {
	id: string;
	label: string;
	notes?: string;
	purposes?: ('llm' | 'vision')[];
	enabled?: boolean;
	// v1.98: 推奨度は用途ごとに持つ。recommendation_level は旧形式の読み取り用。
	recommendation_llm?: number;
	recommendation_vision?: number;
	recommendation_level?: number;
	speed_class?: string;
	speed_label?: string;
	comment_ja?: string;
	comment_en?: string;
	// v1.98: 提供元が提供終了したモデル。一覧には残すが新規描画では選べない。
	eol?: boolean;
	eol_date?: string;
};

export type ProviderGroup = {
	id: Provider;
	label: string;
	kind?: string;
	builtin?: boolean;
	requires_api_key?: boolean;
	memo?: string;
	models: ModelOption[];
};

// Model ids here are bare, exactly as the server catalog states them. They used
// to be written qualified for some providers and bare for others, which left no
// way to ask "which providers list this model".
export const PROVIDER_GROUPS: ProviderGroup[] = [
	{
		id: 'openai',
		label: 'OpenAI API Platform',
		models: [
			{ id: 'gpt-5.1', label: 'GPT-5.1' },
			{ id: 'gpt-5.1-mini', label: 'GPT-5.1 mini' },
			{ id: 'gpt-4.1', label: 'GPT-4.1' },
			{ id: 'gpt-4.1-mini', label: 'GPT-4.1 mini' }
		]
	},
	{
		id: 'nvidia',
		label: 'NVIDIA NIM',
		models: [
			{ id: 'google/gemma-4-31b-it', label: 'Google Gemma 4 31B Instruct' },
			{ id: 'meta/llama-3.3-70b-instruct', label: 'Meta Llama 3.3 70B Instruct' },
			{ id: 'mistralai/mistral-large-2-instruct', label: 'Mistral AI Mistral Large 2 Instruct' }
		]
	},
	{
		id: 'anthropic',
		label: 'Claude API',
		models: [
			{ id: 'claude-opus-4-7', label: 'Anthropic Claude Opus 4.7' },
			{ id: 'claude-sonnet-4-6', label: 'Anthropic Claude Sonnet 4.6' },
			{ id: 'claude-haiku-4-5-20251001', label: 'Anthropic Claude Haiku 4.5' }
		]
	},
	{
		id: 'gemini',
		label: 'Gemini API',
		models: [
			{ id: 'gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
			{ id: 'gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
			{ id: 'gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash-Lite' }
		]
	},
	{
		id: 'ollama',
		label: 'Ollama',
		models: [
			{ id: 'llama3.2', label: 'Llama 3.2' },
			{ id: 'gpt-oss:20b', label: 'gpt-oss 20B' },
			{ id: 'qwen3:8b', label: 'Qwen3 8B' }
		]
	},
	{
		id: 'ollama-cloud',
		label: 'Ollama Cloud (ollama.com)',
		models: [
			{ id: 'gemma4:31b', label: 'gemma4:31b' },
			{ id: 'qwen3.5:397b', label: 'qwen3.5:397b' },
			{ id: 'glm-5.2', label: 'glm-5.2' }
		]
	},
	{
		id: 'ovms',
		label: 'Intel OVMS',
		models: [
			{ id: 'qwen3-api', label: 'Qwen3 8B Instruct', notes: 'thinking有効' },
			{ id: 'qwen-api', label: 'Qwen2.5 7B Instruct' },
			{ id: 'gemma3-12b-api', label: 'Google Gemma 3 12B Instruct', notes: '低速' },
			{ id: 'gemma3-4b-api', label: 'Google Gemma 3 4B Instruct' }
		]
	}
];

export const DEFAULT_PROVIDER: Provider = 'nvidia';
export const DEFAULT_MODEL = 'google/gemma-4-31b-it';

export function modelsForProvider(provider: Provider): ModelOption[] {
	return PROVIDER_GROUPS.find((g) => g.id === provider)?.models ?? [];
}

// The catalog the resolution rules read when a caller does not name one. It
// starts as the built-in list and grows as the server catalogs arrive, so the
// ~40 call sites of qualifiedModelId() stay correct for providers the operator
// added without threading a catalog through every one of them.
let registeredProviderIds = new Set<Provider>(PROVIDER_GROUPS.map((group) => group.id));
let registeredModelOwners = ownersOf(PROVIDER_GROUPS);

function ownersOf(groups: ProviderGroup[]): Map<string, Set<Provider>> {
	const owners = new Map<string, Set<Provider>>();
	for (const group of groups) {
		for (const model of group.models) {
			const seen = owners.get(model.id) ?? new Set<Provider>();
			seen.add(group.id);
			owners.set(model.id, seen);
		}
	}
	return owners;
}

/** Teach the rules about the providers and models this server actually serves. */
export function registerModelCatalog(groups: ProviderGroup[]): void {
	if (!Array.isArray(groups) || groups.length === 0) return;
	const ids = new Set<Provider>(registeredProviderIds);
	const owners = new Map<string, Set<Provider>>(registeredModelOwners);
	for (const group of groups) {
		ids.add(group.id);
		for (const model of group.models) {
			const seen = new Set<Provider>(owners.get(model.id) ?? []);
			seen.add(group.id);
			owners.set(model.id, seen);
		}
	}
	registeredProviderIds = ids;
	registeredModelOwners = owners;
}

/**
 * Split "provider:model"; provider is null when the reference is not qualified.
 *
 * Written with indexOf/slice on purpose. `'a:b:c'.split(':', 1)` returns
 * `['a']` in JavaScript -- the limit drops the tail instead of capping the
 * number of splits the way Python's `split(':', 1)` does, so the model id
 * would silently lose everything after its own colon.
 */
export function splitModelRef(
	ref: string,
	groups?: ProviderGroup[]
): { provider: Provider | null; model: string } {
	const text = String(ref ?? '');
	const index = text.indexOf(':');
	if (index <= 0) return { provider: null, model: text };
	const head = text.slice(0, index);
	const rest = text.slice(index + 1);
	const known = groups ? new Set(groups.map((group) => group.id)) : registeredProviderIds;
	if (rest && known.has(head)) return { provider: head, model: rest };
	return { provider: null, model: text };
}

/**
 * Prefix the provider unless the reference is already qualified by a *known*
 * provider. Testing only for one's own id produced 'ollama:ollama-cloud:...'.
 */
export function qualifiedModelId(provider: Provider, modelId: string, groups?: ProviderGroup[]): string {
	const cleanProvider = String(provider || '').trim();
	const cleanModel = String(modelId || '').trim();
	if (!cleanProvider || !cleanModel) return cleanModel;
	return splitModelRef(cleanModel, groups).provider ? cleanModel : `${cleanProvider}:${cleanModel}`;
}

/**
 * Resolve a reference to (provider, model). Same three rules as the server's
 * provider_for_model(): explicit qualification, then sole ownership, then the
 * stage default. Nothing is guessed from the shape of the string.
 */
export function resolveModelRef(
	modelId: string,
	groups?: ProviderGroup[],
	stageProvider: Provider = DEFAULT_PROVIDER
): { provider: Provider; model: string } {
	const split = splitModelRef(modelId, groups);
	if (split.provider) return { provider: split.provider, model: split.model };
	const owners = groups ? ownersOf(groups).get(split.model) : registeredModelOwners.get(split.model);
	if (owners && owners.size === 1) return { provider: [...owners][0], model: split.model };
	return { provider: stageProvider, model: split.model };
}

export function providerOfModel(
	modelId: string,
	groups?: ProviderGroup[],
	stageProvider: Provider = DEFAULT_PROVIDER
): Provider {
	return resolveModelRef(modelId, groups, stageProvider).provider;
}
