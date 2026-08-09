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
	/** Old id -> the id it answers to today. Absent on servers before the rename table. */
	renamed_catalog_ids?: Record<string, string>;
};

/**
 * How a work's catalog should be named on screen.
 *
 * `retired` means nothing current answers to that id. It is a statement about
 * the nameplate only: the work still draws, in the colors recorded on the work
 * itself, so naming it "inku Default" -- which is what a bare lookup falls back
 * to -- would name a catalog it was never drawn with.
 */
export type CatalogNameplate = { name: string; retired: boolean };

export function catalogNameplate(
	catalogs: ColorCatalog[],
	renamed: Record<string, string>,
	id: string | null | undefined,
	storedName?: string | null
): CatalogNameplate {
	if (!id) return { name: FALLBACK_CATALOG.name, retired: false };
	const current = catalogById(catalogs, renamed[id] ?? id);
	if (current) return { name: current.name, retired: false };
	return { name: storedName || id, retired: true };
}

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
