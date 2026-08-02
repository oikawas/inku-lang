// How many extra passes a batch makes over the lines that failed.
// Key, default, parser and state stay together -- see
// features/color-catalog/settings.svelte.ts for why.
import { registerPersistedSetting } from '$lib/features/persisted-settings';

const BATCH_RETRY_KEY = 'inku-batch-retry';

// Zero by default: a batch keeps behaving exactly as it did before this setting
// existed until the author turns it on. A default of 1 would silently double the
// model spend of every failing batch for people who never opened the setting.
const DEFAULT_MAX_RETRIES = 0;
export const BATCH_RETRY_MIN = 0;
export const BATCH_RETRY_MAX = 5;

function normalize(value: number): number {
	if (!Number.isFinite(value)) return DEFAULT_MAX_RETRIES;
	return Math.min(BATCH_RETRY_MAX, Math.max(BATCH_RETRY_MIN, Math.trunc(value)));
}

class BatchSettings {
	maxRetries = $state(DEFAULT_MAX_RETRIES);

	// The caller owns the try/catch (see color-catalog).
	load = () => {
		const raw = localStorage.getItem(BATCH_RETRY_KEY);
		if (raw !== null) this.maxRetries = normalize(Number(raw));
	};

	setMaxRetries = (value: number) => {
		this.maxRetries = normalize(value);
		try {
			localStorage.setItem(BATCH_RETRY_KEY, String(this.maxRetries));
		} catch {
			/* private mode / quota: the count is still applied in memory */
		}
	};
}

export const batchSettings = new BatchSettings();

// Restored at start-up with every other persisted setting.
registerPersistedSetting({ id: 'batch', load: batchSettings.load });
