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
	// 提供元の有料プランでしか叩けないモデル。EOL と同じく選べないが、理由が違う
	// (退役したのではなく、こちらの契約が届いていない)。
	requires_subscription?: boolean;
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
		// API のカタログが届くまでの控え。verified_model_catalog.py の
		// VERIFIED_OLLAMA_LOCAL_MODELS と同じ並び・同じ id を保つこと。
		// 実測のコメントと速度は API 側から来るのでここには持たない。
		// 量子化までタグに書くのは、素タグが上流で差し替わり計測と結びつかなくなるため。
		models: [
			{ id: 'qwen3.5:4b-q4_K_M', label: 'qwen3.5:4b-q4_K_M (3.4GB)' },
			{
				id: 'ministral-3:8b-instruct-2512-q4_K_M',
				label: 'ministral-3:8b-instruct-2512-q4_K_M (6.0GB)'
			},
			{ id: 'gemma4:e4b-it-q4_K_M', label: 'gemma4:e4b-it-q4_K_M (9.6GB)' },
			{ id: 'gemma4:31b-it-q4_K_M', label: 'gemma4:31b-it-q4_K_M (19GB)' },
			{ id: 'gemma4:12b-it-q4_K_M', label: 'gemma4:12b-it-q4_K_M (7.6GB)' },
			{ id: 'qwen3.5:27b-q4_K_M', label: 'qwen3.5:27b-q4_K_M (17GB)' },
			{ id: 'qwen3.5:9b-q4_K_M', label: 'qwen3.5:9b-q4_K_M (6.6GB)' },
			{ id: 'granite4.1:8b-q4_K_M', label: 'granite4.1:8b-q4_K_M (5.3GB)' },
			{ id: 'qwen3.5:2b-q4_K_M', label: 'qwen3.5:2b-q4_K_M (1.9GB)' },
			{ id: 'qwen3.5:0.8b-q8_0', label: 'qwen3.5:0.8b-q8_0 (1.0GB)' }
		]
	},
	{
		id: 'ollama-cloud',
		label: 'Ollama Cloud (ollama.com)',
		// サーバのカタログが届くまでの控え。**無料枠で叩ける 3 本を推奨度の高い順に置く。**
		// 以前はここに qwen3.5:397b と glm-5.2 を並べていたが、どちらも提供元の有料プランが
		// 要る (2026-07-29 実測・403)。控えには印が付かないので、起動直後だけ選べてしまい、
		// 描こうとして初めて壁に気づくことになる。
		models: [
			{ id: 'nemotron-3-ultra', label: 'nemotron-3-ultra' },
			{ id: 'minimax-m2.5', label: 'minimax-m2.5' },
			{ id: 'nemotron-3-super', label: 'nemotron-3-super' }
		]
	}
];

// Providers withdrawn from the catalog. They are offered nowhere -- every picker
// reads PROVIDER_GROUPS -- but artworks made before the withdrawal still name
// their models, and the name is the only thing left to honour: without an entry
// here the six ovms artworks would read "NVIDIA NIM / ovms:gemma3-4b-api", which
// is worse than the id alone because it also names the wrong machine.
//
// A retired provider takes part in *naming* and never in *routing*: its ids are
// recognised when a reference is split (so "ovms:x" is not read as a bare model)
// and its labels are looked up for display, but it is kept out of the ownership
// table, so rule 2 can never send new work to an endpoint that stopped serving.
const RETIRED_PROVIDER_GROUPS: ProviderGroup[] = [
	{
		// Intel OVMS, the local OpenAI-compatible backend until 2026-07-30.
		// Six artworks name gemma3-4b-api: five as 'ovms:gemma3-4b-api', one bare
		// (measured 2026-07-30). No artwork names the other three models.
		id: 'ovms',
		label: 'Intel OVMS',
		models: [
			{ id: 'qwen3-api', label: 'Qwen3 8B Instruct' },
			{ id: 'qwen-api', label: 'Qwen2.5 7B Instruct' },
			{ id: 'gemma3-12b-api', label: 'Google Gemma 3 12B Instruct' },
			{ id: 'gemma3-4b-api', label: 'Google Gemma 3 4B Instruct' }
		]
	}
];

const retiredProviderIds = new Set<Provider>(RETIRED_PROVIDER_GROUPS.map((group) => group.id));

export const DEFAULT_PROVIDER: Provider = 'nvidia';
export const DEFAULT_MODEL = 'google/gemma-4-31b-it';

export function modelsForProvider(provider: Provider): ModelOption[] {
	return PROVIDER_GROUPS.find((g) => g.id === provider)?.models ?? [];
}

// The catalog the resolution rules read when a caller does not name one. It
// starts as the built-in list and grows as the server catalogs arrive, so the
// ~40 call sites of qualifiedModelId() stay correct for providers the operator
// added without threading a catalog through every one of them.
// Retired ids join the id set and both label maps, and stay out of the owner
// map: naming, never routing.
let registeredProviderIds = new Set<Provider>(
	[...PROVIDER_GROUPS, ...RETIRED_PROVIDER_GROUPS].map((group) => group.id)
);
let registeredModelOwners = ownersOf(PROVIDER_GROUPS);
let registeredProviderLabels = providerLabelsOf([...PROVIDER_GROUPS, ...RETIRED_PROVIDER_GROUPS]);
let registeredModelLabels = modelLabelsOf([...PROVIDER_GROUPS, ...RETIRED_PROVIDER_GROUPS]);
const retiredModelOwners = ownersOf(RETIRED_PROVIDER_GROUPS);

function providerLabelsOf(groups: ProviderGroup[]): Map<Provider, string> {
	const labels = new Map<Provider, string>();
	for (const group of groups) if (group.label) labels.set(group.id, group.label);
	return labels;
}

function modelLabelsOf(groups: ProviderGroup[]): Map<string, string> {
	const labels = new Map<string, string>();
	for (const group of groups) {
		for (const model of group.models) if (model.label) labels.set(`${group.id}:${model.id}`, model.label);
	}
	return labels;
}

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
	registeredProviderLabels = new Map([...registeredProviderLabels, ...providerLabelsOf(groups)]);
	registeredModelLabels = new Map([...registeredModelLabels, ...modelLabelsOf(groups)]);
}

/** The provider's own name, falling back to its id when the catalog has none. */
export function providerLabel(provider: Provider, groups?: ProviderGroup[]): string {
	const id = String(provider ?? '');
	if (!id) return '';
	const fromArgument = groups?.find((group) => group.id === id)?.label;
	return fromArgument || registeredProviderLabels.get(id) || id;
}

/**
 * How a model is named on screen: "<provider> / <model>".
 *
 * A model id alone does not say where it runs, and since gpt-oss:20b is served
 * by two providers the name is not even unique. Every place that shows a model
 * to a person goes through here.
 */
export function modelDisplayName(
	modelId: string | null | undefined,
	groups?: ProviderGroup[],
	stageProvider: Provider = DEFAULT_PROVIDER
): string {
	const ref = String(modelId ?? '').trim();
	if (!ref) return '';
	const { provider, model } = resolveModelRefForDisplay(ref, groups, stageProvider);
	const fromArgument = groups?.find((group) => group.id === provider)?.models.find((item) => item.id === model)?.label;
	const name = fromArgument || registeredModelLabels.get(`${provider}:${model}`) || model;
	const owner = providerLabel(provider, groups);
	return owner ? `${owner} / ${name}` : name;
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
	// Retired ids are recognised whichever catalog is handed in: "ovms:gemma3-4b-api"
	// must never be read as a bare model id whose name happens to contain a colon.
	const known = groups
		? new Set<Provider>([...groups.map((group) => group.id), ...retiredProviderIds])
		: registeredProviderIds;
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

/**
 * Resolve a reference the way a *label* should read it: the same three rules,
 * with retired ownership consulted between rule 2 and rule 3.
 *
 * Kept separate from resolveModelRef() so the retired entries can name an old
 * artwork without ever becoming a place new work is sent. Only the two functions
 * that produce text for a person go through here.
 */
export function resolveModelRefForDisplay(
	modelId: string,
	groups?: ProviderGroup[],
	stageProvider: Provider = DEFAULT_PROVIDER
): { provider: Provider; model: string } {
	const split = splitModelRef(modelId, groups);
	if (split.provider) return { provider: split.provider, model: split.model };
	const owners = groups ? ownersOf(groups).get(split.model) : registeredModelOwners.get(split.model);
	if (owners && owners.size === 1) return { provider: [...owners][0], model: split.model };
	const retired = retiredModelOwners.get(split.model);
	if (retired && retired.size === 1) return { provider: [...retired][0], model: split.model };
	return { provider: stageProvider, model: split.model };
}
