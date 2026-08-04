import { DEFAULT_MODEL, DEFAULT_PROVIDER } from '$lib/models';

export type DemoSettings = {
	save_db: boolean;
	save_files: boolean;
	prompt_provider: string;
	prompt_model: string;
	seed_phrase: string;
	interval_seconds: number;
	timeout_seconds: number;
};

export const DEFAULT_DEMO_SETTINGS: DemoSettings = {
	save_db: false,
	save_files: false,
	prompt_provider: DEFAULT_PROVIDER,
	prompt_model: DEFAULT_MODEL,
	seed_phrase: '日本の四季を感じさせる文章を40語以内で生成',
	interval_seconds: 30,
	timeout_seconds: 3600,
};
