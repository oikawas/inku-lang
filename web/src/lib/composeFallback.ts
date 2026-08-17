// 作曲フォールバック (Stage 2). Single source for what the record means and for
// what a sender writes into it.
//
// Stage 2 turns the DDL into a Score. When it cannot, a deterministic fallback
// writes one instead, and the work that comes out was not composed from the
// words -- the same break Stage 1 already marks. Until this column the fact
// lived only in one response and was gone the moment the work was saved.
//
// Three readings, not two:
//
//   a reason string -- the stage fell, and the string says why
//   'none'         -- a writer said the stage held
//   null / absent  -- nobody wrote it down (the work predates the column)
//
// The middle one is why the writers are asked to speak either way. Stage 1's
// column has no 'none', so its null carries both of the last two meanings at
// once; that is not fixed here, because changing it would rewrite what the 33
// existing rows say.

export const COMPOSE_FALLBACK_NONE = 'none';

/** What the record says about one work's compose stage. */
export type ComposeFallbackState = 'yes' | 'no' | 'unrecorded';

/** The reason a work's score came from the fallback, or `null` when it did not
 *  or when nothing was recorded. This is the mark's condition: 'none' and an
 *  absent record both mean "no mark", for different reasons. */
export function composeFallbackReason(value: unknown): string | null {
	if (typeof value !== 'string') return null;
	const trimmed = value.trim();
	if (!trimmed || trimmed === COMPOSE_FALLBACK_NONE) return null;
	return trimmed;
}

/** The three states, kept apart. The provenance drawer shows this; the mark
 *  does not, because a badge on every older work would say nothing about the
 *  work and would wear out the badge that does. */
export function composeFallbackState(value: unknown): ComposeFallbackState {
	if (typeof value !== 'string' || !value.trim()) return 'unrecorded';
	return value.trim() === COMPOSE_FALLBACK_NONE ? 'no' : 'yes';
}

/** What a sender writes when it saves a work it has a paint response for.
 *
 *  The same rule the server applies on the paint route
 *  (`api_core/rendering.py:compose_fallback_value`): always a string. Omitting
 *  the key stores NULL, and NULL already means "drawn before the column", so a
 *  silent sender makes a sound work look unrecorded. */
export function composeFallbackValue(result: {
	compose_fallback_used?: boolean | null;
	compose_retry_reasons?: string[] | null;
}): string {
	if (!result?.compose_fallback_used) return COMPOSE_FALLBACK_NONE;
	for (const reason of result.compose_retry_reasons ?? []) {
		if (typeof reason === 'string' && reason.trim()) return reason.trim();
	}
	return 'stage2_fallback';
}

/** Whether a work carries the fallback mark, reading both layers.
 *
 *  One derivation for every place that draws the mark. Two copies of this
 *  condition would let a listing and a canvas disagree about the same work,
 *  and only one of them would be corrected when the rule moves. */
export function hasFallbackMark(work: {
	interpret_fallback?: string | null;
	compose_fallback?: string | null;
}): boolean {
	return Boolean(work?.interpret_fallback) || composeFallbackReason(work?.compose_fallback) !== null;
}
