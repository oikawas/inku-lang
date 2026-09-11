import { normalizeCaptionPosition, normalizeCaptionWritingMode, type CaptionPosition, type CaptionWritingMode } from '$lib/captionWritingMode';
import { registerUserSettingsContributor } from '$lib/features/user-settings';

class CaptionSettings {
	writingMode = $state<CaptionWritingMode>('horizontal');
	position = $state<CaptionPosition>('left');

	setWritingMode = (mode: CaptionWritingMode) => {
		this.writingMode = normalizeCaptionWritingMode(mode);
		persist({ instruction_caption_writing_mode: this.writingMode });
	};

	setPosition = (position: CaptionPosition) => {
		this.position = normalizeCaptionPosition(position);
		persist({ instruction_caption_position: this.position });
	};
}

export const captionSettings = new CaptionSettings();

let persist: (fields: Record<string, string>) => void = () => {};

export function bindCaptionSettingsPersist(write: typeof persist): void {
	persist = write;
}

registerUserSettingsContributor({
	id: 'caption',
	collect: () => ({
		instruction_caption_writing_mode: captionSettings.writingMode,
		instruction_caption_position: captionSettings.position
	}),
	apply: (settings) => {
		captionSettings.writingMode = normalizeCaptionWritingMode(settings.instruction_caption_writing_mode);
		captionSettings.position = normalizeCaptionPosition(settings.instruction_caption_position);
	}
});
