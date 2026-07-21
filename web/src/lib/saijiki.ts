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

// English surfaces of the same table (GET /api/saijiki?lang=en). Display
// components keep reading SAIJIKI; this store exists so highlighting can match
// English DDL regardless of the UI language (instruction_lang can differ from
// it). There is no codegen snapshot for it, so it stays empty until hydration.
export let SAIJIKI_EN: SaijikiCategory[] = [];

export function hydrateSaijikiEn(categories: SaijikiCategory[]): void {
	SAIJIKI_EN = categories;
}
