/**
 * Whether the generation-information drawer follows the history strip: with
 * it on, choosing another work from the strip while the drawer is open keeps
 * the drawer open, and the drawer shows the work just chosen.
 *
 * Plain .ts (no runes), so the parsing and the press test are testable without
 * the compiler -- the same split features/describe-panel/folds.ts uses.
 */

/** Key as the server stores it inside `model_settings`. */
export const FOLLOW_FIELD = 'generation_info_follows_selection';

/** On for an account that never chose: it is the reason the setting exists. */
export const FOLLOW_DEFAULT = true;

/** The attribute a history-strip work carries; pressing it chooses that work. */
export const SELECTS_WORK_ATTRIBUTE = 'data-selects-work';

export function followFromSettings(settings: Record<string, unknown> | null | undefined): boolean {
	const stored = settings?.[FOLLOW_FIELD];
	return typeof stored === 'boolean' ? stored : FOLLOW_DEFAULT;
}

type Pressed = { closest: (selector: string) => unknown } | null;

/**
 * A press that chooses another work from the history strip. A control inside
 * the work (its star) does not choose it, so it closes the drawer as any other
 * press outside does.
 */
export function pressChoosesWork(target: Pressed): boolean {
	if (!target || typeof target.closest !== 'function') return false;
	if (!target.closest(`[${SELECTS_WORK_ATTRIBUTE}]`)) return false;
	return !target.closest('button');
}
