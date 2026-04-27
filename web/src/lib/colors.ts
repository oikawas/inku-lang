export type ColorKey = 'white' | 'black' | 'blue' | 'red' | 'green' | 'gray';
export type ColorMap = Record<ColorKey, string>;

export type ColorCatalog = {
	id: string;
	name: string;
	sub: string;
	map: ColorMap;
	swatches: string[]; // 8 colors for display
};

// 規定値 — renderer.py の COLOR_MAP と一致
export const DEFAULT_COLOR_MAP: ColorMap = {
	white: '#ffffff',
	black: '#111111',
	blue:  '#2c3e91',
	red:   '#a2342a',
	green: '#2f6b3a',
	gray:  '#888888',
};

export const COLOR_CATALOGS: ColorCatalog[] = [
	{
		id: 'default',
		name: 'inku Default',
		sub: '規定値',
		map: DEFAULT_COLOR_MAP,
		swatches: ['#111111', '#ffffff', '#2c3e91', '#a2342a', '#2f6b3a', '#888888', '#555555', '#eeeeee'],
	},
	{
		id: 'japanese',
		name: 'Japanese Tradition',
		sub: '和の伝統色',
		map: { black: '#111111', white: '#fffffb', red: '#a2342a', blue: '#2c3e91', green: '#2f6b3a', gray: '#888888' },
		swatches: ['#111111', '#fffffb', '#a2342a', '#2c3e91', '#2f6b3a', '#888888', '#a591c5', '#ffb61e'],
	},
	{
		id: 'renaissance',
		name: 'Italian Renaissance',
		sub: 'Rinascimento',
		map: { black: '#5d4037', white: '#f5f5f5', red: '#e34234', blue: '#003399', green: '#4f7942', gray: '#a0522d' },
		swatches: ['#a0522d', '#003399', '#e34234', '#f7e89f', '#4f7942', '#daa520', '#f5f5f5', '#5d4037'],
	},
	{
		id: 'impressionism',
		name: 'French Impressionism',
		sub: 'Impressionnisme',
		map: { black: '#2a52be', white: '#ffffff', red: '#ffc1cc', blue: '#87ceeb', green: '#40826d', gray: '#c8a2c8' },
		swatches: ['#2a52be', '#ffc1cc', '#ffce00', '#40826d', '#c8a2c8', '#87ceeb', '#ffffff', '#fbceb1'],
	},
	{
		id: 'chinese',
		name: 'Chinese Imperial',
		sub: '中国伝統色',
		map: { black: '#1a1a1b', white: '#fffdfa', red: '#ee1c25', blue: '#0040ff', green: '#00a86b', gray: '#800080' },
		swatches: ['#ee1c25', '#ffb612', '#00a86b', '#0040ff', '#800080', '#fffdfa', '#1a1a1b', '#ff4d00'],
	},
	{
		id: 'nordic',
		name: 'Scandinavian Minimalism',
		sub: 'Nordic',
		map: { black: '#2c3e50', white: '#fcfcfc', red: '#a98467', blue: '#5dade2', green: '#4b5d43', gray: '#95a5a6' },
		swatches: ['#fcfcfc', '#2c3e50', '#4b5d43', '#95a5a6', '#e5e8e8', '#5dade2', '#f4d03f', '#a98467'],
	},
	{
		id: 'indian',
		name: 'Indian Spice',
		sub: 'Masala',
		map: { black: '#000080', white: '#ffffff', red: '#e30b5c', blue: '#fc0fc0', green: '#666600', gray: '#c19a6b' },
		swatches: ['#ff9933', '#ffcc00', '#e30b5c', '#666600', '#000080', '#fc0fc0', '#c19a6b', '#ffffff'],
	},
	{
		id: 'egyptian',
		name: 'Egyptian Sands',
		sub: 'Kemetic',
		map: { black: '#0a0a0a', white: '#f5deb3', red: '#b31b1b', blue: '#123499', green: '#40e0d0', gray: '#cc7722' },
		swatches: ['#123499', '#ffd700', '#b31b1b', '#40e0d0', '#f5deb3', '#0a0a0a', '#cc7722', '#e8e4c9'],
	},
	{
		id: 'mexican',
		name: 'Mexican Vibrant',
		sub: 'Fiesta',
		map: { black: '#1c1c1c', white: '#f4f4f4', red: '#f50087', blue: '#73c2fb', green: '#008f39', gray: '#b04a33' },
		swatches: ['#f50087', '#73c2fb', '#008f39', '#ff9800', '#b04a33', '#fff200', '#f4f4f4', '#1c1c1c'],
	},
	{
		id: 'british',
		name: 'British Heritage',
		sub: 'Traditional',
		map: { black: '#000080', white: '#fffdd0', red: '#dc143c', blue: '#4169e1', green: '#004225', gray: '#708090' },
		swatches: ['#004225', '#4169e1', '#708090', '#dc143c', '#8b8589', '#fffdd0', '#dcdcdc', '#000080'],
	},
	{
		id: 'greek',
		name: 'Greek Aegean',
		sub: 'Kykládes',
		map: { black: '#191970', white: '#ffffff', red: '#e2725b', blue: '#005bae', green: '#808000', gray: '#b2beb5' },
		swatches: ['#ffffff', '#89cff0', '#005bae', '#b2beb5', '#808000', '#f9d71c', '#e2725b', '#191970'],
	},
];

export function getCatalogById(id: string): ColorCatalog | undefined {
	return COLOR_CATALOGS.find((c) => c.id === id);
}

export function getColorMap(catalogId: string): ColorMap {
	return getCatalogById(catalogId)?.map ?? DEFAULT_COLOR_MAP;
}
