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

/**
 * The line under the catalog's name in the generation info: what that catalog
 * holds, in the language being read.
 *
 * The work carries the tagline in the words it had when it was drawn, and that
 * copy is English -- the server stores `catalog["sub"]` whatever the UI is
 * speaking. The Japanese copy exists (`sub_ja`, and the catalog API sends it),
 * so the two can be paired up: when the catalog still answers to its id and its
 * English tagline is still the one on the work, the Japanese line is the same
 * statement and can be read instead.
 *
 * When they differ, the definition moved after the work was drawn, and the
 * stored line is the historical one. That is provenance, so it is shown as it
 * stands rather than quietly replaced with today's wording.
 */
export function catalogSubLine(
	catalogs: ColorCatalog[],
	renamed: Record<string, string>,
	id: string | null | undefined,
	storedSub: string,
	isJapanese: boolean
): string {
	if (!storedSub || !isJapanese || !id) return storedSub;
	const current = catalogById(catalogs, renamed[id] ?? id);
	if (!current || current.sub !== storedSub) return storedSub;
	return current.sub_ja || storedSub;
}

/** The colour words in the order the saijiki lists them, so a work's map is
 *  read in the same order wherever it is shown. */
export const COLOR_KEY_ORDER: ColorKey[] = [
	'white',
	'black',
	'blue',
	'red',
	'green',
	'gray',
	'yellow',
	'orange',
	'purple'
];

const COLOR_KEY_JA: Record<ColorKey, string> = {
	white: '白',
	black: '黒',
	blue: '青',
	red: '赤',
	green: '緑',
	gray: '灰',
	yellow: '黄',
	orange: '橙',
	purple: '紫'
};

/** A colour word in the language being read. The keys are the saijiki's own
 *  colour vocabulary, so the Japanese side is the saijiki word, not a gloss. */
export function colorWordLabel(key: string, isJapanese: boolean): string {
	if (!isJapanese) return key;
	return COLOR_KEY_JA[key as ColorKey] ?? key;
}

/**
 * A work's colour map as pairs, in saijiki order, skipping what it does not
 * carry. An empty list means the work has no map recorded -- which is not the
 * same as a map of nine defaults.
 *
 * Only the colour words. `render_color_map` also carries a `palette:<name>`
 * entry for every colour in the catalog's palette (color_catalogs.py builds it
 * that way, and renderer.py reads those entries to pick chromatic and
 * achromatic tones). Those are the catalog's own list of pigments copied onto
 * the work, keyed by an English display name; the question this row answers is
 * which colour each colour word was drawn in, and that is the nine.
 */
export function colorMapEntries(map: ColorMap | null | undefined): { key: string; code: string }[] {
	if (!map) return [];
	return COLOR_KEY_ORDER.filter((key) => map[key]).map((key) => ({ key, code: map[key] as string }));
}
