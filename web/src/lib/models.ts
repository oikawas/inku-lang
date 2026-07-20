export type Provider = string;

export type ModelOption = {
	id: string;
	label: string;
	notes?: string;
	purposes?: ('llm' | 'vision')[];
	enabled?: boolean;
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

export const PROVIDER_GROUPS: ProviderGroup[] = [
	{
		id: 'openai',
		label: 'OpenAI API Platform',
		models: [
			{ id: 'openai:gpt-5.1', label: 'GPT-5.1' },
			{ id: 'openai:gpt-5.1-mini', label: 'GPT-5.1 mini' },
			{ id: 'openai:gpt-4.1', label: 'GPT-4.1' },
			{ id: 'openai:gpt-4.1-mini', label: 'GPT-4.1 mini' }
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
			{ id: 'anthropic:claude-opus-4-7', label: 'Anthropic Claude Opus 4.7' },
			{ id: 'anthropic:claude-sonnet-4-6', label: 'Anthropic Claude Sonnet 4.6' },
			{ id: 'anthropic:claude-haiku-4-5-20251001', label: 'Anthropic Claude Haiku 4.5' }
		]
	},
	{
		id: 'gemini',
		label: 'Gemini API',
		models: [
			{ id: 'gemini:gemini-2.5-pro', label: 'Gemini 2.5 Pro' },
			{ id: 'gemini:gemini-2.5-flash', label: 'Gemini 2.5 Flash' },
			{ id: 'gemini:gemini-2.5-flash-lite', label: 'Gemini 2.5 Flash-Lite' }
		]
	},
	{
		id: 'ollama',
		label: 'Ollama',
		models: [
			{ id: 'ollama:llama3.2', label: 'Llama 3.2' },
			{ id: 'ollama:gpt-oss:20b', label: 'gpt-oss 20B' },
			{ id: 'ollama:qwen3:8b', label: 'Qwen3 8B' }
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

export function qualifiedModelId(provider: Provider, modelId: string): string {
	const cleanProvider = String(provider || '').trim();
	const cleanModel = String(modelId || '').trim();
	if (!cleanProvider || !cleanModel) return cleanModel;
	return cleanModel.startsWith(`${cleanProvider}:`) ? cleanModel : `${cleanProvider}:${cleanModel}`;
}

export function providerOfModel(modelId: string): Provider {
	if (modelId.startsWith('openai:')) return 'openai';
	if (modelId.startsWith('anthropic:')) return 'anthropic';
	if (modelId.startsWith('gemini:')) return 'gemini';
	if (modelId.startsWith('nvidia:')) return 'nvidia';
	if (modelId.startsWith('ollama:')) return 'ollama';
	if (modelId.startsWith('ovms:')) return 'ovms';
	if (modelId.includes(':') && !modelId.startsWith('gpt-oss:')) return modelId.split(':', 1)[0];
	for (const g of PROVIDER_GROUPS) {
		if (g.models.some((m) => m.id === modelId)) return g.id;
	}
	return 'nvidia';
}
