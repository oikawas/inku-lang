// Whether the generation-information drawer stays open when another work is
// chosen from the history strip. Key, default and parsing live in
// ./generation-info-follow.ts (plain .ts, testable without the rune compiler);
// this file holds only the live state.
//
// It rides in the user's `model_settings` on the server, like the describe
// panel's folds: see features/user-settings.ts.
//
// Whether the drawer shows each stage's tokens beside the work's total rides
// the same way; its key and parsing live in ./generation-info-tokens.ts.
import { FOLLOW_DEFAULT, FOLLOW_FIELD, followFromSettings } from '$lib/features/canvas/generation-info-follow';
import { TOKEN_DETAIL_DEFAULT, TOKEN_DETAIL_FIELD, tokenDetailFromSettings } from '$lib/features/canvas/generation-info-tokens';
import { registerUserSettingsContributor } from '$lib/features/user-settings';

class GenerationInfoSettings {
	followsSelection = $state(FOLLOW_DEFAULT);
	tokenDetail = $state(TOKEN_DETAIL_DEFAULT);

	setFollowsSelection = (follows: boolean) => {
		this.followsSelection = follows;
		persist({ [FOLLOW_FIELD]: follows });
	};

	setTokenDetail = (detail: boolean) => {
		this.tokenDetail = detail;
		persist({ [TOKEN_DETAIL_FIELD]: detail });
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
	collect: () => ({
		[FOLLOW_FIELD]: generationInfoSettings.followsSelection,
		[TOKEN_DETAIL_FIELD]: generationInfoSettings.tokenDetail
	}),
	apply: (settings) => {
		generationInfoSettings.followsSelection = followFromSettings(settings);
		generationInfoSettings.tokenDetail = tokenDetailFromSettings(settings);
	}
});
