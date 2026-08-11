import {
	DEFAULT_ANIMATION_EXPORT_SETTINGS,
	parseAnimationExportSettings,
	type AnimationExportSettings
} from '$lib/animationExport';
import {
	DEFAULT_CARD_EXPORT_SETTINGS,
	parseCardExportSettings,
	type CardExportSettings
} from '$lib/cardExport';
import { registerPersistedSetting } from '$lib/features/persisted-settings';

// Export settings that survive a reload.  They are written back as a group by a
// single $effect in the page, so adding one here needs no edit anywhere else --
// see features/color-catalog/settings.svelte.ts for why that matters.
const PNG_ALPHA_KEY = 'inku-png-alpha-white';
const ANIMATION_EXPORT_SETTINGS_KEY = 'inku-animation-export-settings';
const CARD_EXPORT_SETTINGS_KEY = 'inku-card-export-settings';

class ExportSettings {
	pngAlphaWhite = $state(false);
	animation = $state<AnimationExportSettings>({ ...DEFAULT_ANIMATION_EXPORT_SETTINGS });
	card = $state<CardExportSettings>({ ...DEFAULT_CARD_EXPORT_SETTINGS });
	private loaded = $state(false);

	// The caller owns the try/catch (see color-catalog).
	load = () => {
		const alpha = localStorage.getItem(PNG_ALPHA_KEY);
		if (alpha !== null) this.pngAlphaWhite = alpha === '1';
		this.animation = parseAnimationExportSettings(localStorage.getItem(ANIMATION_EXPORT_SETTINGS_KEY));
		this.card = parseCardExportSettings(localStorage.getItem(CARD_EXPORT_SETTINGS_KEY));
	};

	// Called once the whole load block has run, so a failure part-way through it
	// leaves persistence off exactly as it did before.
	markLoaded = () => {
		this.loaded = true;
	};

	persist = () => {
		// Read every persisted field before the guard: the $effect that calls
		// this has to keep tracking them on the runs before load(), otherwise the
		// first change afterwards would never be written.
		void this.pngAlphaWhite;
		void this.animation;
		void this.card;
		if (!this.loaded) return;
		try {
			localStorage.setItem(PNG_ALPHA_KEY, this.pngAlphaWhite ? '1' : '0');
			localStorage.setItem(ANIMATION_EXPORT_SETTINGS_KEY, JSON.stringify(this.animation));
			localStorage.setItem(CARD_EXPORT_SETTINGS_KEY, JSON.stringify(this.card));
		} catch {
			/* private mode / quota: the settings still apply to this session */
		}
	};
}

export const exportSettings = new ExportSettings();

// Restored at start-up with every other persisted setting.
registerPersistedSetting({ id: 'export', load: exportSettings.load, afterLoad: exportSettings.markLoaded });
