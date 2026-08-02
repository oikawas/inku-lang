import {
	registerRenderContributor,
	type RenderContributor,
	type RenderOverrides
} from '../render-payload.ts';

export const WILD_CONTRIBUTOR_ID = 'wild';

type WildOverride = {
	enabled?: boolean | null;
};

/**
 * Override the switch for one request.  `null` means "omit the field": a
 * compose or a re-render of a stored score inherits what the artwork was drawn
 * with rather than what is switched on now.
 */
export function wildOverride(enabled: boolean | null | undefined): RenderOverrides {
	return { [WILD_CONTRIBUTOR_ID]: { enabled: enabled ?? null } };
}

let readEnabled: () => boolean = () => false;

export function bindWildRenderState(read: () => boolean): void {
	readEnabled = read;
}

export const wildContributor: RenderContributor = {
	id: WILD_CONTRIBUTOR_ID,
	payload: (kind, override) => {
		if (kind === 'render-score') return {};
		const given = override as WildOverride | undefined;
		const explicit = given && 'enabled' in given ? given.enabled : undefined;
		// A fresh paint always states the switch; the others carry it only when
		// the caller resolved one, so an omission still means "inherit".
		if (kind === 'paint') return { wild: (explicit === undefined ? readEnabled() : explicit) ?? false };
		return explicit != null ? { wild: explicit } : {};
	}
};

registerRenderContributor(wildContributor);
