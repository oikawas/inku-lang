export type ColorKey =
	| 'white'
	| 'black'
	| 'blue'
	| 'red'
	| 'green'
	| 'gray'
	| 'yellow'
	| 'orange'
	| 'purple';
export type ColorMap = Partial<Record<ColorKey, string>>;

export type ColorCatalog = {
	id: string;
	name: string;
	sub: string;
	sub_ja?: string;
	map: ColorMap;
	swatches: string[];
	palette: { name: string; name_ja?: string; code: string }[];
};

export type ColorCatalogsResponse = {
	default_catalog_id: string;
	catalogs: ColorCatalog[];
};

export const FALLBACK_CATALOG: ColorCatalog = {
	id: 'default',
	name: 'inku Default',
	sub: 'neutral baseline',
	sub_ja: 'ニュートラルな基準値',
	map: {},
	swatches: [],
	palette: [],
};

export function catalogById(catalogs: ColorCatalog[], id: string): ColorCatalog | undefined {
	return catalogs.find((catalog) => catalog.id === id);
}
