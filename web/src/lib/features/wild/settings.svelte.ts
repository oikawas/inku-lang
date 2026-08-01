// 暴れる (engine 12): OFF = 予想のつく標準、ON = 天井を外した奔放なストローク。
// One switch for the whole artwork, persisted.  Key, default and state stay
// together -- see features/color-catalog/settings.svelte.ts for why.
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
