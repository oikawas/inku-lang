/** The choices returned for a saved work. Null means it was not recorded. */
export type RecordedDrawOptions = {
	route: 'read_and_draw' | 'stages' | null;
	sketch: 'on' | 'off' | null;
	composition: 'on' | 'off' | null;
	wild: 'on' | 'off' | null;
	catalog: { id: string | null; mode: string | null } | null;
	canvas_aspect: string | null;
	models: { stage1?: string | null; stage2?: string | null; vision?: string | null } | null;
};

export const DRAW_OPTIONS = ['route', 'sketch', 'composition', 'wild', 'catalog', 'canvas_aspect', 'models'] as const;
export type DrawTab = 'describe' | 'image' | 'batch_text' | 'batch_image';
export type DrawOptions = {
	route: 'read_and_draw' | 'stages';
	sketch: 'on' | 'off';
	composition: 'on' | 'off';
	wild: 'on' | 'off';
	catalog: { id: string; mode: 'fixed' | 'auto' };
	canvas_aspect: string;
	models: { stage1?: string; stage2?: string; vision?: string };
};
export type DrawDefaults = Record<DrawTab, DrawOptions>;

/** Apply the core's missing-value rule to the already-projected server record. */
export function optionsForWork(record: RecordedDrawOptions | null | undefined, defaults: DrawOptions, tab: DrawTab): DrawOptions {
	const image = tab === 'image' || tab === 'batch_image';
	const catalog = record?.catalog;
	return {
		route: record?.route ?? defaults.route,
		sketch: record?.sketch ?? 'off',
		composition: record?.composition ?? 'off',
		wild: record?.wild ?? 'off',
		catalog: { id: catalog?.id ?? defaults.catalog.id,
			mode: catalog?.mode === 'auto' ? 'auto' : catalog?.mode ? 'fixed' : defaults.catalog.mode },
		canvas_aspect: record?.canvas_aspect ?? defaults.canvas_aspect,
		models: image ? { vision: record?.models?.vision ?? defaults.models.vision }
			: { stage1: record?.models?.stage1 ?? defaults.models.stage1, stage2: record?.models?.stage2 ?? defaults.models.stage2 },
	};
}

export function copyDrawOptions(options: DrawOptions): DrawOptions {
	return { ...options, catalog: { ...options.catalog }, models: { ...options.models } };
}

export function copyDrawDefaults(defaults: DrawDefaults): DrawDefaults {
	return { describe: copyDrawOptions(defaults.describe), image: copyDrawOptions(defaults.image),
		batch_text: copyDrawOptions(defaults.batch_text), batch_image: copyDrawOptions(defaults.batch_image) };
}

export function migrateLegacyWild(defaults: DrawDefaults, raw: string | null): DrawDefaults | null {
	if (raw !== '0' && raw !== '1') return null;
	const migrated = copyDrawDefaults(defaults);
	for (const options of Object.values(migrated)) options.wild = raw === '1' ? 'on' : 'off';
	return migrated;
}

export function drawOptionRows(options: RecordedDrawOptions | null | undefined, labels: import('../i18n/types.ts').LangPack) {
	const names = { route: labels.drawDefaultsRoute, sketch: labels.sketchLabel, composition: labels.drawDefaultsComposition,
		wild: labels.wildButton, catalog: labels.colorCatalogButton, canvas_aspect: labels.drawDefaultsCanvas, models: labels.drawDefaultsModel };
	return DRAW_OPTIONS.map((key) => {
		const value = options?.[key];
		let text = 'N/A';
		if (typeof value === 'string') {
			text = value === 'on' ? labels.drawDefaultsOn : value === 'off' ? labels.drawDefaultsOff
				: value === 'read_and_draw' ? labels.drawDefaultsRead : value === 'stages' ? labels.drawDefaultsStages : value;
		} else if (key === 'catalog' && options?.catalog) {
			const catalog = options.catalog;
			text = `${catalog.id ?? 'N/A'} (${catalog.mode === 'auto' ? labels.colorCatalogAuto : catalog.mode === 'fixed' ? labels.drawDefaultsFixed : catalog.mode ?? 'N/A'})`;
		} else if (key === 'models' && options?.models) {
			const models = options.models;
			text = models.vision ?? (models.stage1 === models.stage2 ? models.stage1 : [models.stage1, models.stage2].map((v) => v ?? 'N/A').join(' / ')) ?? 'N/A';
		}
		return { key, label: names[key], text };
	});
}
