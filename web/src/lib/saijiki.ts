import { GENERATED_SAIJIKI, GENERATED_SAIJIKI_EN } from './saijiki.generated';

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

// English surfaces of the same table (GET /api/saijiki?lang=en). Highlighting
// matches English DDL regardless of the UI language (instruction_lang can
// differ from it), and the saijiki panels take their display words from here
// when the UI is English. The server derives both position-aligned lists from
// bilingual word entries, so index i is the same entry in either language.
export let SAIJIKI_EN: SaijikiCategory[] = GENERATED_SAIJIKI_EN.map((cat) => ({
	...cat,
	words: [...cat.words]
}));

export function hydrateSaijikiEn(categories: SaijikiCategory[]): void {
	SAIJIKI_EN = categories;
}

/** Display words for a category in the current UI language. */
export function saijikiWordsFor(categoryKey: string, isJapanese: boolean): string[] {
	const source = isJapanese ? SAIJIKI : SAIJIKI_EN;
	return source.find((cat) => cat.key === categoryKey)?.words ?? [];
}
