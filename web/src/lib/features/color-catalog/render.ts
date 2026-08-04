import {
	registerRenderContributor,
	type RenderContributor,
	type RenderOverrides
} from '../render-payload.ts';

export const COLOR_CATALOG_CONTRIBUTOR_ID = 'color-catalog';

/**
 * The selection value that means "let the server read the description".
 *
 * It is not a catalog: no palette answers to it and `catalogById` never finds
 * it.  It lives in the same slot as a catalog id because the choice is one
 * choice -- the modal offers it above the thirteen -- but it must never leave
 * the client as a `catalog_id`.  `resolveCatalogId` is the only exit.
 */
export const AUTO_CATALOG_ID = 'auto';

export type CatalogMode = 'fixed' | 'auto' | 'random';

/** What the contributor may be told to use instead of the live selection. */
type CatalogOverride = {
	selected?: string | null;
	mode?: CatalogMode;
};

/**
 * Override the catalog for one request.  A batch freezes the selection before
 * its first line, and every refinement redraws against the artwork's own
 * catalog rather than whatever is selected now -- both go through here.
 */
export function colorCatalogOverride(selected: string | null | undefined, mode?: CatalogMode): RenderOverrides {
	return { [COLOR_CATALOG_CONTRIBUTOR_ID]: { selected, mode } };
}

/** Live state, lent by the settings module (which owns the rune). */
let readSelected: () => string = () => 'default';

export function bindColorCatalogRenderState(read: () => string): void {
	readSelected = read;
}

/**
 * Where `auto` lands when the server cannot read the description, and what
 * every non-paint request is handed instead of the sentinel.  The page lends
 * the catalog list's own default so this file does not name a second one.
 */
let readFallback: () => string = () => 'default';

export function bindColorCatalogFallback(read: () => string): void {
	readFallback = read;
}

/** A real catalog id, always: the sentinel resolves to the fallback. */
export function resolveCatalogId(selected: string | null | undefined): string {
	const id = (selected ?? '').trim();
	if (!id || id === AUTO_CATALOG_ID) return readFallback();
	return id;
}

export function isAutoCatalog(selected: string | null | undefined): boolean {
	return selected === AUTO_CATALOG_ID;
}

export const colorCatalogContributor: RenderContributor = {
	id: COLOR_CATALOG_CONTRIBUTOR_ID,
	payload: (kind, override) => {
		const given = override as CatalogOverride | undefined;
		const requested = given?.selected ?? readSelected();
		const auto = isAutoCatalog(requested);
		// Resolved here so the sentinel cannot reach an endpoint: the non-paint
		// ones have no mode to carry it, and `auto` is not a catalog the server
		// could look up -- it would answer 422.
		const catalogId = resolveCatalogId(requested);
		// Only the paint endpoint decides the catalog for itself; the others are
		// handed a resolved id.
		if (kind === 'paint') return { catalog_id: catalogId, catalog_mode: auto ? 'auto' : (given?.mode ?? 'fixed') };
		return { catalog_id: catalogId };
	}
};

registerRenderContributor(colorCatalogContributor);
