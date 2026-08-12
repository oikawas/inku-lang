/**
 * The field names, defaults and parsing for the describe panel's two folds:
 * 写生 (Stage 0.5) and 展開後 (Stage 2 input).
 *
 * Plain .ts (no runes), so both sides of the round trip are testable without
 * the compiler -- the same split features/color-catalog/render.ts uses.
 */

/** Keys as the server stores them inside `model_settings`. */
export const SKETCH_FIELD = 'sketch_open';
export const DDL_EXPANDED_FIELD = 'ddl_expanded_open';

/**
 * Each section keeps its own default, and they differ.  The sketch prose was
 * always visible before it could be folded, so an account that has never
 * folded it keeps seeing what it saw; the expanded DDL has always started
 * folded, so it keeps starting folded.
 */
export const SKETCH_DEFAULT = true;
export const DDL_EXPANDED_DEFAULT = false;

export type DescribePanelFolds = {
	sketchOpen: boolean;
	ddlExpandedOpen: boolean;
};

export const DEFAULT_FOLDS: DescribePanelFolds = {
	sketchOpen: SKETCH_DEFAULT,
	ddlExpandedOpen: DDL_EXPANDED_DEFAULT
};

/**
 * A stored fold, or this section's own default when the user has none.
 *
 * The fallback is per call, not one shared constant: a section that defaults
 * open and a section that defaults folded must not collapse into each other
 * the moment a user has no stored value.
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
		ddlExpandedOpen: storedFold(settings, DDL_EXPANDED_FIELD, DDL_EXPANDED_DEFAULT)
	};
}

/** The fields the server stores, for a save that carries both. */
export function foldsToSettings(folds: DescribePanelFolds): Record<string, boolean> {
	return {
		[SKETCH_FIELD]: folds.sketchOpen,
		[DDL_EXPANDED_FIELD]: folds.ddlExpandedOpen
	};
}
