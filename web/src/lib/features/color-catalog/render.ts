import {
	registerRenderContributor,
	type RenderContributor,
	type RenderOverrides
} from '../render-payload.ts';

export const COLOR_CATALOG_CONTRIBUTOR_ID = 'color-catalog';

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

export const colorCatalogContributor: RenderContributor = {
	id: COLOR_CATALOG_CONTRIBUTOR_ID,
	payload: (kind, override) => {
		const given = override as CatalogOverride | undefined;
		const catalogId = given?.selected ?? readSelected();
		// Only the paint endpoint decides the catalog for itself; the others are
		// handed a resolved id.
		if (kind === 'paint') return { catalog_id: catalogId, catalog_mode: given?.mode ?? 'fixed' };
		return { catalog_id: catalogId };
	}
};

registerRenderContributor(colorCatalogContributor);
