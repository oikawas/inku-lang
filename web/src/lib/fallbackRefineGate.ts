// Asking before refining from a work whose words were lost.
//
// A work drawn by a fallback -- Stage 1's or Stage 2's -- is not an answer to
// the description it is filed under. Refining from it carries that break into
// every descendant, and the lineage panel shows the child as a continuation of
// the words all the same. So the author is asked, once, before the first
// refinement of such a work.
//
// Once, not every time: the second refinement is the author continuing a
// decision already made, and a dialog that reappears becomes a key to press
// rather than a thing to read. The memory lives on the screen, not in the
// database -- it is about this sitting, not about the work.

import { hasFallbackMark } from './composeFallback';

export type FallbackRefineParent = {
	id?: string | null;
	interpret_fallback?: string | null;
	compose_fallback?: string | null;
} | null | undefined;

/** Whether refining from this parent should be confirmed first. */
export function needsFallbackRefineConfirm(parent: FallbackRefineParent, asked: Set<string>): boolean {
	if (!parent || !hasFallbackMark(parent)) return false;
	const id = fallbackRefineKey(parent);
	// No id yet -- an unsaved work being refined in place. It cannot be
	// remembered, so it is asked about again rather than waved through: the
	// question is about the break, and the break is still there.
	if (!id) return true;
	return !asked.has(id);
}

/** Remember that this parent was asked about and answered. */
export function rememberFallbackRefineConfirm(parent: FallbackRefineParent, asked: Set<string>): void {
	const id = fallbackRefineKey(parent);
	if (id) asked.add(id);
}

function fallbackRefineKey(parent: FallbackRefineParent): string {
	return typeof parent?.id === 'string' && parent.id ? parent.id : '';
}
