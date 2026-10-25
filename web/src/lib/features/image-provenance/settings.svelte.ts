import { registerPersistedSetting } from '$lib/features/persisted-settings';
import { DEFAULT_IMAGE_PROVENANCE_OPTIONS, parseImageProvenanceOptions, type ImageProvenanceOptions } from './provenance';

// What the image tab writes into the source note when an image is chosen.
// A preference of this browser, kept like the export settings.
const IMAGE_PROVENANCE_SETTINGS_KEY = 'inku-image-provenance-settings';

class ImageProvenanceSettings {
	options = $state<ImageProvenanceOptions>({ ...DEFAULT_IMAGE_PROVENANCE_OPTIONS });
	private loaded = $state(false);

	// The caller owns the try/catch (see color-catalog).
	load = () => {
		this.options = parseImageProvenanceOptions(localStorage.getItem(IMAGE_PROVENANCE_SETTINGS_KEY));
	};

	markLoaded = () => {
		this.loaded = true;
	};

	persist = () => {
		// Read before the guard so the $effect keeps tracking it before load().
		void this.options;
		if (!this.loaded) return;
		try {
			localStorage.setItem(IMAGE_PROVENANCE_SETTINGS_KEY, JSON.stringify(this.options));
		} catch {
			/* private mode / quota: the settings still apply to this session */
		}
	};
}

export const imageProvenanceSettings = new ImageProvenanceSettings();

registerPersistedSetting({ id: 'image-provenance', load: imageProvenanceSettings.load, afterLoad: imageProvenanceSettings.markLoaded });
