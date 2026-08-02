/**
 * Which settings are restored from localStorage at start-up.
 *
 * The page used to name each one: a block of `X.load()` calls that a new
 * setting had to be added to.  A feature now registers its own load and the
 * page calls the block once.
 *
 * This file names no feature.  Features register themselves on import, which
 * the page's existing imports already cause.
 */
export type PersistedSetting = {
	id: string;
	load: () => void;
	/**
	 * Run after every load has succeeded.  A setting that only starts writing
	 * once the whole block has run registers its latch here, so a failure
	 * part-way through still leaves persistence off exactly as it did before.
	 */
	afterLoad?: () => void;
};

const settings: PersistedSetting[] = [];

export function registerPersistedSetting(setting: PersistedSetting): void {
	// Re-registering the same id replaces it: a hot reload must not double up.
	const at = settings.findIndex((s) => s.id === setting.id);
	if (at >= 0) settings[at] = setting;
	else settings.push(setting);
}

/** Ids of everything currently registered, in registration order. */
export function persistedSettingIds(): string[] {
	return settings.map((s) => s.id);
}

/**
 * Restore every registered setting.
 *
 * This does not catch: the caller owns the try/catch, and a storage failure
 * must abort the whole block -- leaving the settings after it at their
 * defaults -- exactly as it did when the page listed the calls by hand.
 */
export function loadPersistedSettings(): void {
	for (const setting of settings) setting.load();
	for (const setting of settings) setting.afterLoad?.();
}
