// Wild (engine 12): OFF is predictable and standard; ON removes the ceiling
// for uninhibited strokes.
// One switch for the whole artwork, persisted.  Key, default and state stay
// together -- see features/color-catalog/settings.svelte.ts for why.
import { bindWildRenderState } from '$lib/features/wild/render';
import { registerPersistedSetting } from '$lib/features/persisted-settings';

const WILD_KEY = 'inku-wild';

class WildSettings {
	enabled = $state(false);

	// The caller owns the try/catch (see color-catalog).
	load = () => {
		const raw = localStorage.getItem(WILD_KEY);
		if (raw !== null) this.enabled = raw === '1';
	};

	set = (value: boolean) => {
		this.enabled = value;
		try {
			localStorage.setItem(WILD_KEY, value ? '1' : '0');
		} catch {
			/* private mode / quota: the switch is still applied in memory */
		}
	};
}

export const wildSettings = new WildSettings();

// The render slice lives in ./render.ts; it reads the live switch through this.
bindWildRenderState(() => wildSettings.enabled);

// Restored at start-up with every other persisted setting.
registerPersistedSetting({ id: 'wild', load: wildSettings.load });
