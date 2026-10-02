// Whether sketch from life (Stage 0.5) is open. Key, default, state and both sides of the round
// trip live together -- see features/color-catalog/settings.svelte.ts for why.
//
// These ride in the user's `model_settings` on the server rather than in
// localStorage, for the same reason the colour catalogue does: the section
// has anything to show without a session, so a browser-wide value would only
// ever be the wrong user's. See features/user-settings.ts.
//
// The keys, defaults and parsing live in ./folds.ts (plain .ts, so they are
// testable without the rune compiler); this file holds only the live state.
import {
	foldsFromSettings,
	foldsToSettings,
	SKETCH_DEFAULT,
	SKETCH_FIELD
} from '$lib/features/describe-panel/folds';
import { registerUserSettingsContributor } from '$lib/features/user-settings';

class DescribePanelSettings {
	sketchOpen = $state(SKETCH_DEFAULT);

	toggleSketch = () => {
		this.sketchOpen = !this.sketchOpen;
		persist({ [SKETCH_FIELD]: this.sketchOpen });
	};

	/**
	 * Editing the sketch prose needs it on screen.  Opening this way is saved
	 * like any other open: the author asked to see it, and would be surprised
	 * to find it folded again next time.
	 */
	revealSketch = () => {
		if (this.sketchOpen) return;
		this.toggleSketch();
	};
}

export const describePanelSettings = new DescribePanelSettings();

// The page lends the write because it owns `apiFetch` and the current user.
let persist: (fields: Record<string, boolean>) => void = () => {};

export function bindDescribePanelPersist(write: (fields: Record<string, boolean>) => void): void {
	persist = write;
}

// Restored with the rest of the user's settings at login.  A user who has never
// folded anything gets the defaults -- and so does the next user on this
// browser, which is why the reset is not conditional.
registerUserSettingsContributor({
	id: 'describe-panel',
	collect: () =>
		foldsToSettings({
			sketchOpen: describePanelSettings.sketchOpen
		}),
	apply: (settings) => {
		const folds = foldsFromSettings(settings);
		describePanelSettings.sketchOpen = folds.sketchOpen;
	}
});
