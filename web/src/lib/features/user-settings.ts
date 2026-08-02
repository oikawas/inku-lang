/**
 * Which settings ride along in the user's `model_settings` on the server.
 *
 * The page used to name each feature's field three times -- in the type it
 * declares, where it restores a user, and where it saves one -- so a new
 * server-persisted setting cost three edits here plus one in the feature.
 * A feature now owns all three and the page carries the slice.
 *
 * The rest of `model_settings` (the model choices themselves) still belongs to
 * the page; this only collects what features own.  No API field is renamed:
 * a contributor emits the same keys the server already stores.
 */
export type UserSettingsSlice = Record<string, unknown>;

export type UserSettingsContributor = {
	id: string;
	/** The feature's fields, as the server stores them. */
	collect: () => UserSettingsSlice;
	/** Restore from a stored `model_settings`; it may hold nothing for us. */
	apply: (settings: UserSettingsSlice) => void;
};

const contributors: UserSettingsContributor[] = [];

export function registerUserSettingsContributor(contributor: UserSettingsContributor): void {
	// Re-registering the same id replaces it: the page rebuilds its features on
	// a hot reload, and a second copy would fight the first over the same keys.
	const at = contributors.findIndex((c) => c.id === contributor.id);
	if (at >= 0) contributors[at] = contributor;
	else contributors.push(contributor);
}

/** Ids of everything currently contributing, in registration order. */
export function userSettingsContributorIds(): string[] {
	return contributors.map((c) => c.id);
}

/** Every feature's fields, to be merged into what the page saves. */
export function collectUserSettings(): UserSettingsSlice {
	const collected: UserSettingsSlice = {};
	for (const contributor of contributors) Object.assign(collected, contributor.collect());
	return collected;
}

/**
 * Hand a stored `model_settings` to every feature.  Each one applies its own
 * fields, including resetting to its default when the user has none -- so a
 * user without the setting still clears whatever the previous user left.
 */
export function applyUserSettings(settings: UserSettingsSlice | null | undefined): void {
	for (const contributor of contributors) contributor.apply(settings ?? {});
}
