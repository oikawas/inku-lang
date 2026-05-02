export const CANVAS_ASPECT_PLUGIN_ID = 'canvas-aspect';
export const DEFAULT_CANVAS_ASPECT_ID = 'square';

export type CanvasAspectId =
	| 'square'
	| 'golden'
	| 'a4'
	| 'b4'
	| 'pillar'
	| 'oban'
	| 'wide'
	| 'vertical';

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

export const CANVAS_ASPECT_OPTIONS: CanvasAspectOption[] = [
	{ id: 'square', category: 'Basic', label: 'Square', ratio: '1:1', ratioW: 1, ratioH: 1, intentJa: '標準仕様。完全な秩序を象徴する正方形。', intentEn: 'Default square format, a symbol of complete order.' },
	{ id: 'golden', category: 'Standard', label: 'Golden', ratio: '1.618:1', ratioW: 1.618, ratioH: 1, intentJa: '西洋美術における伝統的な美の比率。', intentEn: 'Traditional Western proportion of beauty.' },
	{ id: 'a4', category: 'Modern', label: 'A4', ratio: '1:1.414', ratioW: 1, ratioH: 1.414, intentJa: '日本でも馴染み深い印刷規格のルート長方形。', intentEn: 'Root rectangle familiar through modern print standards.' },
	{ id: 'b4', category: 'Modern', label: 'B4', ratio: '1:1.414', ratioW: 1, ratioH: 1.414, intentJa: '印刷物の身体感を持つルート長方形。', intentEn: 'Root rectangle with a physical print sensibility.' },
	{ id: 'pillar', category: 'Classic JP', label: 'Pillar', ratio: '1:5', ratioW: 1, ratioH: 5, intentJa: '柱絵。縦長の余白と書き下ろしの感覚。', intentEn: 'Japanese pillar-picture format with tall negative space.' },
	{ id: 'oban', category: 'Ukiyoe', label: 'Oban', ratio: '2:3', ratioW: 2, ratioH: 3, intentJa: '浮世絵木版画の標準的な比率。', intentEn: 'Standard ukiyo-e oban woodblock proportion.' },
	{ id: 'wide', category: 'Cinema', label: 'Wide', ratio: '2.35:1', ratioW: 2.35, ratioH: 1, intentJa: 'シネマスコープ。パノラマや情景の提示。', intentEn: 'Cinemascope panorama for scenes and landscapes.' },
	{ id: 'vertical', category: 'Mobile', label: 'Vertical', ratio: '9:16', ratioW: 9, ratioH: 16, intentJa: 'スマートフォン全画面の現代的な型。', intentEn: 'Contemporary full-screen mobile format.' },
];

export function normalizeCanvasAspectId(value: unknown): CanvasAspectId {
	return CANVAS_ASPECT_OPTIONS.some((option) => option.id === value)
		? value as CanvasAspectId
		: DEFAULT_CANVAS_ASPECT_ID;
}

export function getCanvasAspectOption(value: unknown): CanvasAspectOption {
	const id = normalizeCanvasAspectId(value);
	return CANVAS_ASPECT_OPTIONS.find((option) => option.id === id) ?? CANVAS_ASPECT_OPTIONS[0];
}
