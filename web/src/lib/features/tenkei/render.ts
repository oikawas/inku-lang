import {
	registerRenderContributor,
	type RenderContributor,
	type RenderOverrides
} from '../render-payload.ts';
import { DEFAULT_TENKEI, type TenkeiLevel } from '../../tenkei.ts';

export const TENKEI_CONTRIBUTOR_ID = 'tenkei';

type TenkeiOverride = {
	level?: TenkeiLevel | null;
};

/**
 * Override the level for one request.  `null` means "omit the field", which is
 * how a refinement or a lineage child inherits its parent's level -- see
 * lib/tenkei.ts for the server's resolution order.
 */
export function tenkeiOverride(level: TenkeiLevel | null | undefined): RenderOverrides {
	return { [TENKEI_CONTRIBUTOR_ID]: { level: level ?? null } };
}

let readLevel: () => TenkeiLevel = () => DEFAULT_TENKEI;

export function bindTenkeiRenderState(read: () => TenkeiLevel): void {
	readLevel = read;
}

export const tenkeiContributor: RenderContributor = {
	id: TENKEI_CONTRIBUTOR_ID,
	payload: (kind, override) => {
		if (kind !== 'paint' && kind !== 'compose') return {};
		const given = override as TenkeiOverride | undefined;
		// A fresh paint states the level; a compose inherits unless told
		// otherwise, so only `paint` falls back to the live setting.
		const level = given && 'level' in given ? given.level : (kind === 'paint' ? readLevel() : null);
		return level ? { tenkei: level } : {};
	}
};

registerRenderContributor(tenkeiContributor);
