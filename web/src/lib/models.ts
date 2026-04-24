export type ModelOption = {
	id: string;
	label: string;
	notes?: string;
};

export const MODELS: ModelOption[] = [
	{ id: 'qwen3-api', label: 'Qwen3-8B', notes: 'thinking抑制 (/no_think)' },
	{ id: 'qwen-api', label: 'Qwen2.5-7B' },
	{ id: 'gemma3-4b-api', label: 'Gemma3-4B' },
	{ id: 'gemma3-12b-api', label: 'Gemma3-12B', notes: '重い (1-2分/推論)' }
];

export const DEFAULT_STAGE1_MODEL = 'qwen3-api';
export const DEFAULT_STAGE2_MODEL = 'qwen-api';
