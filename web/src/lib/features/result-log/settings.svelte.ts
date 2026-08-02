// Whether the result log panel under the canvas is expanded.  Key, default and
// state stay together -- see features/color-catalog/settings.svelte.ts for why.
import { registerPersistedSetting } from '$lib/features/persisted-settings';

const RESULT_LOG_OPEN_KEY = 'inku-result-log-open';

class ResultLogSettings {
	open = $state(false);

	// The caller owns the try/catch (see color-catalog).
	load = () => {
		this.open = localStorage.getItem(RESULT_LOG_OPEN_KEY) === '1';
	};

	toggle = () => {
		this.open = !this.open;
		try {
			localStorage.setItem(RESULT_LOG_OPEN_KEY, this.open ? '1' : '0');
		} catch {
			/* private mode / quota: the panel still opens */
		}
	};
}

export const resultLogSettings = new ResultLogSettings();

// Restored at start-up with every other persisted setting.
registerPersistedSetting({ id: 'result-log', load: resultLogSettings.load });
