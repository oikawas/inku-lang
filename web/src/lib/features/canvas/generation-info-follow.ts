/**
 * Whether the generation-information drawer follows work selection: with
 * it on, choosing another work while the drawer is open keeps
 * the drawer open, and the drawer shows the work just chosen.
 *
 * Plain .ts (no runes), so the parsing and the press test are testable without
 * the compiler -- the same split features/describe-panel/folds.ts uses.
 */

/** Key as the server stores it inside `model_settings`. */
export const FOLLOW_FIELD = 'generation_info_follows_selection';

/** On for an account that never chose: it is the reason the setting exists. */
export const FOLLOW_DEFAULT = true;

/** The attribute a work-selection area carries. */
export const SELECTS_WORK_ATTRIBUTE = 'data-selects-work';

export function followFromSettings(settings: Record<string, unknown> | null | undefined): boolean {
	const stored = settings?.[FOLLOW_FIELD];
	return typeof stored === 'boolean' ? stored : FOLLOW_DEFAULT;
}

type Pressed = { closest: (selector: string) => unknown } | null;

/**
 * A work-selection area may itself be a button (a lineage card). Other
 * buttons inside a marked area, such as a history star, are not selection.
 */
export function pressChoosesWork(target: Pressed): boolean {
	if (!target || typeof target.closest !== 'function') return false;
	const selection = target.closest(`[${SELECTS_WORK_ATTRIBUTE}]`);
	if (!selection) return false;
	const button = target.closest('button');
	return !button || button === selection;
}
