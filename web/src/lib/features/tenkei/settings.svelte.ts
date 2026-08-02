import { DEFAULT_TENKEI, normalizeTenkei, type TenkeiLevel } from '$lib/tenkei';
import { bindTenkeiRenderState } from '$lib/features/tenkei/render';
import { registerPersistedSetting } from '$lib/features/persisted-settings';

// 添景水準 (v1.97). Explicit for describe-tab/root generation; refine flows omit
// it to inherit.  Key, default, parser and state stay together -- see
// features/color-catalog/settings.svelte.ts for why.

const TENKEI_KEY = 'inku-tenkei';

class TenkeiSettings {
	level = $state<TenkeiLevel>(DEFAULT_TENKEI);

	// The caller owns the try/catch (see color-catalog).
	load = () => {
		const level = normalizeTenkei(localStorage.getItem(TENKEI_KEY));
		if (level) this.level = level;
	};

	set = (level: TenkeiLevel) => {
		this.level = level;
		try {
			localStorage.setItem(TENKEI_KEY, level);
		} catch {
			/* private mode / quota: the level is still applied in memory */
		}
	};
}

export const tenkeiSettings = new TenkeiSettings();

// The render slice lives in ./render.ts; it reads the live level through this.
bindTenkeiRenderState(() => tenkeiSettings.level);

// Restored at start-up with every other persisted setting.
registerPersistedSetting({ id: 'tenkei', load: tenkeiSettings.load });
