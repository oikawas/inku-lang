export type Provider = 'nvidia' | 'anthropic' | 'local';

export type ModelOption = {
	id: string;
	label: string;
	notes?: string;
};

export type ProviderGroup = {
	id: Provider;
	label: string;
	models: ModelOption[];
};

export const PROVIDER_GROUPS: ProviderGroup[] = [
	{
		id: 'nvidia',
		label: 'NVIDIA NIM',
		models: [
			{ id: 'google/gemma-4-31b-it', label: 'Gemma 4 31B' },
			{ id: 'meta/llama-3.3-70b-instruct', label: 'Llama 3.3 70B' },
			{ id: 'mistralai/mistral-large-2-instruct', label: 'Mistral Large 2' }
		]
	},
	{
		id: 'anthropic',
		label: 'Anthropic',
		models: [
			{ id: 'anthropic:claude-opus-4-7', label: 'Claude Opus 4.7' },
			{ id: 'anthropic:claude-sonnet-4-6', label: 'Claude Sonnet 4.6' },
			{ id: 'anthropic:claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' }
		]
	},
	{
		id: 'local',
		label: 'ローカル (OVMS)',
		models: [
			{ id: 'qwen3-api', label: 'Qwen3-8B', notes: 'thinking有効' },
			{ id: 'qwen-api', label: 'Qwen2.5-7B' },
			{ id: 'gemma3-12b-api', label: 'Gemma3-12B', notes: '低速' },
			{ id: 'gemma3-4b-api', label: 'Gemma3-4B' }
		]
	}
];

export const DEFAULT_PROVIDER: Provider = 'nvidia';
export const DEFAULT_MODEL = 'google/gemma-4-31b-it';

export function modelsForProvider(provider: Provider): ModelOption[] {
	return PROVIDER_GROUPS.find((g) => g.id === provider)?.models ?? [];
}

export function providerOfModel(modelId: string): Provider {
	for (const g of PROVIDER_GROUPS) {
		if (g.models.some((m) => m.id === modelId)) return g.id;
	}
	return 'nvidia';
}
