/**
 * The render request is assembled from slices, one per feature.
 *
 * Before this, every feature that reached the server named its own request
 * fields inside +page.svelte, once per builder -- so a new setting cost one
 * line in each of them.  Here a feature contributes its whole slice and the
 * builders spread it: the page names no feature's request field, and adding a
 * field to a feature is an edit to that feature alone.
 *
 * This file names no feature.  Features register themselves on import.
 */

/**
 * Which request is being built.  The endpoints do not carry the same slices:
 * only `paint` takes the catalog mode, and only `paint`/`compose` take the
 * tenkei level.  A contributor decides what it emits for each kind.
 */
export type RenderRequestKind = 'paint' | 'compose' | 'render-svg' | 'render-score';

/**
 * A caller's per-call override, keyed by contributor id.  The value is a
 * partial of that feature's own state -- never a request field name.  Build
 * one with the feature's own helper (e.g. `wildOverride`) rather than by hand.
 */
export type RenderOverrides = Record<string, Record<string, unknown> | undefined>;

export type RenderContributor = {
	id: string;
	payload: (kind: RenderRequestKind, override: Record<string, unknown> | undefined) => Record<string, unknown>;
};

const contributors: RenderContributor[] = [];

export function registerRenderContributor(contributor: RenderContributor): void {
	// Re-registering the same id replaces it: a hot reload must not double up.
	const at = contributors.findIndex((c) => c.id === contributor.id);
	if (at >= 0) contributors[at] = contributor;
	else contributors.push(contributor);
}

/** Ids of everything currently contributing, in registration order. */
export function renderContributorIds(): string[] {
	return contributors.map((c) => c.id);
}

/**
 * Collect every feature's slice for one request.  Contributors own disjoint
 * fields, so the result does not depend on the order they registered in.
 */
export function renderSettingsPayload(kind: RenderRequestKind, overrides: RenderOverrides = {}): Record<string, unknown> {
	const collected: Record<string, unknown> = {};
	for (const contributor of contributors) {
		Object.assign(collected, contributor.payload(kind, overrides[contributor.id]));
	}
	return collected;
}
