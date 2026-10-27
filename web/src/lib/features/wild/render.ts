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
 * Override the switch for one request. Stored-score replay uses its separate
 * server-owned replay path, which reads the recorded setting.
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
		// A fresh paint states the switch; other paths may supply an explicit value.
		if (kind === 'paint') return { wild: (explicit === undefined ? readEnabled() : explicit) ?? false };
		return explicit != null ? { wild: explicit } : {};
	}
};

registerRenderContributor(wildContributor);
