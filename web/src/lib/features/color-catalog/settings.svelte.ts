// One persisted setting owns its key, its default, its parser and its state.
// Adding a setting must not touch any file another branch is likely to touch:
// the storage key, the reactive state and both sides of the round trip live
// here, so a new setting is a new file (or a new field in this one) instead of
// five edits scattered through +page.svelte.
//
// This one rides in the user's `model_settings` on the server rather than in
// localStorage: a drawing cannot be made without a session (every render route
// is behind `_current_user`), so a browser-wide value would only ever be the
// wrong user's.  See features/user-settings.ts.
import { AUTO_CATALOG_ID, bindColorCatalogRenderState, isAutoCatalog, resolveCatalogId } from '$lib/features/color-catalog/render';
import { registerUserSettingsContributor } from '$lib/features/user-settings';

const CATALOG_FIELD = 'color_catalog_id';
const DEFAULT_CATALOG_ID = 'default';

class ColorCatalogSettings {
	/** What the modal shows as chosen.  May be the `auto` sentinel. */
	selected = $state(DEFAULT_CATALOG_ID);

	get isAuto(): boolean {
		return isAutoCatalog(this.selected);
	}

	/** A real catalog id for everything that stores or sends one. */
	get effectiveId(): string {
		return resolveCatalogId(this.selected);
	}

	/**
	 * Written back to the server when the modal closes.  The page lends the
	 * call because it owns `apiFetch` and the current user.
	 */
	save = () => {
		persist(this.selected);
	};
}

export const colorCatalogSettings = new ColorCatalogSettings();

let persist: (selected: string) => void = () => {};

export function bindColorCatalogPersist(write: (selected: string) => void): void {
	persist = write;
}

// The render slice lives in ./render.ts (plain .ts, so it is testable without
// the rune compiler); it reads the live selection through this.
bindColorCatalogRenderState(() => colorCatalogSettings.selected);

// Restored with the rest of the user's settings at login.  A user who has never
// chosen gets the default -- and so does the next user on this browser, which
// is why the reset is not conditional.
registerUserSettingsContributor({
	id: 'color-catalog',
	collect: () => ({ [CATALOG_FIELD]: colorCatalogSettings.selected }),
	apply: (settings) => {
		const stored = settings[CATALOG_FIELD];
		colorCatalogSettings.selected =
			typeof stored === 'string' && stored.trim() ? stored.trim() : DEFAULT_CATALOG_ID;
	}
});

export { AUTO_CATALOG_ID, DEFAULT_CATALOG_ID };
