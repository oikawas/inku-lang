// Whether the generation-information drawer stays open when another work is
// chosen from the history strip. Key, default and parsing live in
// ./generation-info-follow.ts (plain .ts, testable without the rune compiler);
// this file holds only the live state.
//
// It rides in the user's `model_settings` on the server, like the describe
// panel's folds: see features/user-settings.ts.
import { FOLLOW_DEFAULT, FOLLOW_FIELD, followFromSettings } from '$lib/features/canvas/generation-info-follow';
import { registerUserSettingsContributor } from '$lib/features/user-settings';

class GenerationInfoSettings {
	followsSelection = $state(FOLLOW_DEFAULT);

	setFollowsSelection = (follows: boolean) => {
		this.followsSelection = follows;
		persist({ [FOLLOW_FIELD]: follows });
	};
}

export const generationInfoSettings = new GenerationInfoSettings();

// The page lends the write because it owns `apiFetch` and the current user.
let persist: (fields: Record<string, boolean>) => void = () => {};

export function bindGenerationInfoSettingsPersist(write: (fields: Record<string, boolean>) => void): void {
	persist = write;
}

registerUserSettingsContributor({
	id: 'generation-info',
	collect: () => ({ [FOLLOW_FIELD]: generationInfoSettings.followsSelection }),
	apply: (settings) => {
		generationInfoSettings.followsSelection = followFromSettings(settings);
	}
});
