export const CANVAS_ASPECT_PLUGIN_ID = 'canvas-aspect';
export const DEFAULT_CANVAS_ASPECT_ID = 'square';

export type CanvasAspectId = string;

export type CanvasAspectOption = {
	id: CanvasAspectId;
	category: string;
	label: string;
	ratio: string;
	ratioW: number;
	ratioH: number;
	intentJa: string;
	intentEn: string;
};

export type CanvasFormatRegistryResponse = {
	registry: {
		schema: string;
		formats: Array<{ id: string; width_units: number; height_units: number }>;
	};
	digest: string;
};

type DisplayMetadata = Omit<CanvasAspectOption, 'id' | 'ratio' | 'ratioW' | 'ratioH'>;

// Names and explanatory copy belong to the product UI. Registry membership,
// order, and ratios come only from the shared core response.
const DISPLAY_METADATA: Record<string, DisplayMetadata> = {
	square: { category: 'Basic', label: 'Square', intentJa: '標準仕様。完全な秩序を象徴する正方形。', intentEn: 'Default square format, a symbol of complete order.' },
	golden: { category: 'Standard', label: 'Golden', intentJa: '西洋美術における伝統的な美の比率。', intentEn: 'Traditional Western proportion of beauty.' },
	a4: { category: 'Modern', label: 'A4', intentJa: '日本でも馴染み深い印刷規格のルート長方形。', intentEn: 'Root rectangle familiar through modern print standards.' },
	b4: { category: 'Modern', label: 'B4', intentJa: '印刷物の身体感を持つルート長方形。', intentEn: 'Root rectangle with a physical print sensibility.' },
	pillar: { category: 'Classic JP', label: 'Pillar', intentJa: '柱絵。縦長の余白と書き下ろしの感覚。', intentEn: 'Japanese pillar-picture format with tall negative space.' },
	oban: { category: 'Ukiyoe', label: 'Oban', intentJa: '浮世絵木版画の標準的な比率。', intentEn: 'Standard ukiyo-e oban woodblock proportion.' },
	wide: { category: 'Cinema', label: 'Wide', intentJa: 'シネマスコープ。パノラマや情景の提示。', intentEn: 'Cinemascope panorama for scenes and landscapes.' },
	byobu: { category: 'Classic JP', label: 'Byobu', intentJa: '日本の屏風。六曲一双の一隻に準じる横長の型。', intentEn: 'Japanese folding screen format, based on one half of a six-panel pair.' },
	vertical: { category: 'Mobile', label: 'Vertical', intentJa: 'スマートフォン全画面の現代的な型。', intentEn: 'Contemporary full-screen mobile format.' },
	sd_monitor: { category: 'Display', label: 'SD Monitor', intentJa: '従来型モニターの4:3画面。', intentEn: 'Traditional 4:3 monitor format.' },
	hd_monitor: { category: 'Display', label: 'HD Monitor', intentJa: 'ワイドモニターの16:9画面。', intentEn: 'Widescreen 16:9 monitor format.' },
};

const SQUARE_FALLBACK: CanvasAspectOption = {
	id: DEFAULT_CANVAS_ASPECT_ID,
	category: DISPLAY_METADATA.square.category,
	label: DISPLAY_METADATA.square.label,
	ratio: '1:1',
	ratioW: 1,
	ratioH: 1,
	intentJa: DISPLAY_METADATA.square.intentJa,
	intentEn: DISPLAY_METADATA.square.intentEn,
};

let installedOptions: CanvasAspectOption[] = [SQUARE_FALLBACK];

export function installCanvasFormatRegistry(payload: CanvasFormatRegistryResponse): CanvasAspectOption[] {
	if (!payload.digest || !payload.registry?.schema || !Array.isArray(payload.registry.formats)) {
		throw new Error('invalid_canvas_format_registry');
	}
	const seen = new Set<string>();
	const next = payload.registry.formats.map((format): CanvasAspectOption => {
		if (
			!format.id
			|| seen.has(format.id)
			|| !Number.isSafeInteger(format.width_units)
			|| format.width_units <= 0
			|| !Number.isSafeInteger(format.height_units)
			|| format.height_units <= 0
		) throw new Error('invalid_canvas_format_registry');
		seen.add(format.id);
		const display = DISPLAY_METADATA[format.id] ?? {
			category: 'Other', label: format.id,
			intentJa: format.id, intentEn: format.id,
		};
		return {
			id: format.id,
			...display,
			ratio: `${format.width_units}:${format.height_units}`,
			ratioW: format.width_units,
			ratioH: format.height_units,
		};
	});
	if (!seen.has(DEFAULT_CANVAS_ASPECT_ID)) throw new Error('invalid_canvas_format_registry');
	installedOptions = next;
	return canvasAspectOptions();
}

export function canvasAspectOptions(): CanvasAspectOption[] {
	return installedOptions.map((option) => ({ ...option }));
}

export function normalizeCanvasAspectId(value: unknown): CanvasAspectId {
	return installedOptions.some((option) => option.id === value)
		? value as CanvasAspectId
		: DEFAULT_CANVAS_ASPECT_ID;
}

export function getCanvasAspectOption(value: unknown): CanvasAspectOption {
	const id = normalizeCanvasAspectId(value);
	return installedOptions.find((option) => option.id === id) ?? SQUARE_FALLBACK;
}
