import { GENERATED_SAIJIKI } from './saijiki.generated';

export type SaijikiCategory = {
	key: string;
	label: string;
	en: string;
	words: string[];
};

// Module-level mutable vocabulary store (v1.92 Phase 3). The single source is
// the server saijiki table. This module ships with a codegen snapshot
// (saijiki.generated.ts) as the initial value and is hydrated at runtime from
// GET /api/saijiki after login. Consumers (highlight/SaijikiDrawer/
// SaijikiInline) read SAIJIKI synchronously; a fetch failure leaves the
// snapshot in place rather than degrading the UI.
export let SAIJIKI: SaijikiCategory[] = GENERATED_SAIJIKI.map((cat) => ({
	...cat,
	words: [...cat.words]
}));

export function hydrateSaijiki(categories: SaijikiCategory[]): void {
	SAIJIKI = categories;
}
