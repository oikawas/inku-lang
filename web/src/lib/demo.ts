import { DEFAULT_MODEL } from '$lib/models';

export type DemoSettings = {
	save_db: boolean;
	save_files: boolean;
	prompt_model: string;
	seed_phrase: string;
	interval_seconds: number;
	timeout_seconds: number;
	random_color_catalog: boolean;
};

export const DEFAULT_DEMO_SETTINGS: DemoSettings = {
	save_db: false,
	save_files: false,
	prompt_model: DEFAULT_MODEL,
	seed_phrase: '日本の四季を感じさせる文章を40語以内で生成',
	interval_seconds: 30,
	timeout_seconds: 3600,
	random_color_catalog: false,
};
