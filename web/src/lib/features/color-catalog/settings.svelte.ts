// One persisted setting owns its key, its default, its parser and its state.
// Adding a setting must not touch any file another branch is likely to touch:
// the storage key, the reactive state and both sides of the round trip live
// here, so a new setting is a new file (or a new field in this one) instead of
// five edits scattered through +page.svelte.
import { bindColorCatalogRenderState } from '$lib/features/color-catalog/render';

const CATALOG_KEY = 'inku-color-catalog';

class ColorCatalogSettings {
	selected = $state('default');

	// The caller owns the try/catch: every setting loads inside one block, and a
	// storage failure must abort the whole block exactly as it did before.
	load = () => {
		const raw = localStorage.getItem(CATALOG_KEY);
		if (raw) this.selected = raw;
	};

	save = () => {
		try {
			localStorage.setItem(CATALOG_KEY, this.selected);
		} catch {
			/* private mode / quota: the selection is still applied in memory */
		}
	};
}

export const colorCatalogSettings = new ColorCatalogSettings();

// The render slice lives in ./render.ts (plain .ts, so it is testable without
// the rune compiler); it reads the live selection through this.
bindColorCatalogRenderState(() => colorCatalogSettings.selected);
