// Wild (engine 12): OFF is predictable and standard; ON removes the ceiling
// for uninhibited strokes.
// The saved default and the next drawing's switch are separate.
import { bindWildRenderState } from '$lib/features/wild/render';
import { registerPersistedSetting } from '$lib/features/persisted-settings';

const WILD_DEFAULT_KEY = 'inku-wild-default';

class WildSettings {
	enabled = $state(false);
	selected = $state(false);

	// The caller owns the try/catch (see color-catalog).
	load = () => {
		const raw = localStorage.getItem(WILD_DEFAULT_KEY);
		this.enabled = raw === '1';
		this.selected = this.enabled;
	};

	set = (value: boolean) => {
		this.enabled = value;
		this.selected = value;
		try {
			localStorage.setItem(WILD_DEFAULT_KEY, value ? '1' : '0');
		} catch {
			/* private mode / quota: the switch is still applied in memory */
		}
	};

	setSelected = (value: boolean) => { this.selected = value; };
}

export const wildSettings = new WildSettings();

// The render slice lives in ./render.ts; it reads the live switch through this.
bindWildRenderState(() => wildSettings.selected);

// Restored at start-up with every other persisted setting.
registerPersistedSetting({ id: 'wild', load: wildSettings.load });
