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

/** The options a picture never sends: it has no route, sketch or composition. */
export const TEXT_ONLY_OPTIONS = ['route', 'sketch', 'composition'] as const;

export function isImageTab(tab: DrawTab): boolean {
	return tab === 'image' || tab === 'batch_image';
}

export function copyDrawOptions(options: DrawOptions): DrawOptions {
	return { ...options, catalog: { ...options.catalog }, models: { ...options.models } };
}

export function copyDrawDefaults(defaults: DrawDefaults): DrawDefaults {
	return { describe: copyDrawOptions(defaults.describe), image: copyDrawOptions(defaults.image),
		batch_text: copyDrawOptions(defaults.batch_text), batch_image: copyDrawOptions(defaults.batch_image) };
}

/** The browser-only stroke-limit default of older builds. It is not carried
 *  into the drawing defaults; the page only removes it (author, 2026-11-05). */
export const LEGACY_WILD_DEFAULT_KEY = 'inku-wild-default';

/** How a row names a value the work recorded; ids are shown only when nothing else names them. */
export type DrawOptionNames = {
	catalog?: (id: string) => string;
	canvas?: (id: string) => string;
	model?: (ref: string) => string;
};

export function drawOptionRows(options: RecordedDrawOptions | null | undefined, labels: import('../i18n/types.ts').LangPack,
	view: { image?: boolean; names?: DrawOptionNames } = {}) {
	const names = { route: labels.drawDefaultsRoute, sketch: labels.sketchLabel, composition: labels.drawDefaultsComposition,
		wild: labels.wildButton, catalog: labels.colorCatalogButton, canvas_aspect: labels.drawDefaultsCanvas,
		models: view.image ? labels.drawDefaultsVision : labels.drawDefaultsModel };
	const model = (ref: string | null | undefined) => (ref ? (view.names?.model?.(ref) ?? ref) : labels.drawOptionsUnavailable);
	const keys = DRAW_OPTIONS.filter((key) => !view.image || !(TEXT_ONLY_OPTIONS as readonly string[]).includes(key));
	return keys.map((key) => {
		const value = options?.[key];
		let text = labels.drawOptionsUnavailable;
		if (key === 'canvas_aspect' && typeof value === 'string') {
			text = view.names?.canvas?.(value) ?? value;
		} else if (typeof value === 'string') {
			text = value === 'on' ? labels.drawDefaultsOn : value === 'off' ? labels.drawDefaultsOff
				: value === 'read_and_draw' ? labels.drawDefaultsRead : value === 'stages' ? labels.drawDefaultsStages : value;
		} else if (key === 'catalog' && options?.catalog) {
			const catalog = options.catalog;
			const name = catalog.id ? (view.names?.catalog?.(catalog.id) ?? catalog.id) : labels.drawOptionsUnavailable;
			text = `${name} (${catalog.mode === 'auto' ? labels.colorCatalogAuto : catalog.mode === 'fixed' ? labels.drawDefaultsFixed : labels.drawOptionsUnavailable})`;
		} else if (key === 'models' && options?.models) {
			const models = options.models;
			text = models.vision ? model(models.vision)
				: models.stage1 === models.stage2 ? model(models.stage1)
					: `${model(models.stage1)} / ${model(models.stage2)}`;
		}
		return { key, label: names[key], text };
	});
}
