/**
 * The field names, defaults and parsing for the describe panel's folds: the
 * sketch from life, and the composition and laws (2026-11-13).
 *
 * Plain .ts (no runes), so both sides of the round trip are testable without
 * the compiler -- the same split features/color-catalog/render.ts uses.
 */

/** Keys as the server stores them inside `model_settings`. */
export const SKETCH_FIELD = 'sketch_open';
export const COMPOSITION_FIELD = 'composition_open';

/**
 * The sketch prose was always visible before it could be folded, so an
 * account that has never folded it keeps seeing what it saw.
 */
export const SKETCH_DEFAULT = true;
/** The composition section is new and long; folded, it still shows the thesis and the names. */
export const COMPOSITION_DEFAULT = false;

export type DescribePanelFolds = {
	sketchOpen: boolean;
	compositionOpen: boolean;
};

export const DEFAULT_FOLDS: DescribePanelFolds = {
	sketchOpen: SKETCH_DEFAULT,
	compositionOpen: COMPOSITION_DEFAULT
};

/**
 * A stored fold, or this section's own default when the user has none.
 *
 * Invalid legacy values must not fold prose that defaults open.
 */
export function storedFold(
	settings: Record<string, unknown> | null | undefined,
	field: string,
	fallback: boolean
): boolean {
	const stored = settings?.[field];
	return typeof stored === 'boolean' ? stored : fallback;
}

/** What a stored `model_settings` says, filling each default in separately. */
export function foldsFromSettings(
	settings: Record<string, unknown> | null | undefined
): DescribePanelFolds {
	return {
		sketchOpen: storedFold(settings, SKETCH_FIELD, SKETCH_DEFAULT),
		compositionOpen: storedFold(settings, COMPOSITION_FIELD, COMPOSITION_DEFAULT)
	};
}

/** The current fold fields the server stores. */
export function foldsToSettings(folds: DescribePanelFolds): Record<string, boolean> {
	return {
		[SKETCH_FIELD]: folds.sketchOpen,
		[COMPOSITION_FIELD]: folds.compositionOpen
	};
}
