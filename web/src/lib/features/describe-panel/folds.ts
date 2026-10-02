/**
 * The field name, default and parsing for the sketch-from-life fold.
 *
 * Plain .ts (no runes), so both sides of the round trip are testable without
 * the compiler -- the same split features/color-catalog/render.ts uses.
 */

/** Keys as the server stores them inside `model_settings`. */
export const SKETCH_FIELD = 'sketch_open';

/**
 * The sketch prose was always visible before it could be folded, so an
 * account that has never folded it keeps seeing what it saw.
 */
export const SKETCH_DEFAULT = true;

export type DescribePanelFolds = {
	sketchOpen: boolean;
};

export const DEFAULT_FOLDS: DescribePanelFolds = {
	sketchOpen: SKETCH_DEFAULT
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
		sketchOpen: storedFold(settings, SKETCH_FIELD, SKETCH_DEFAULT)
	};
}

/** The current fold field the server stores. */
export function foldsToSettings(folds: DescribePanelFolds): Record<string, boolean> {
	return {
		[SKETCH_FIELD]: folds.sketchOpen
	};
}
