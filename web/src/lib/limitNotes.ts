/**
 * The limits that took effect on a finished drawing.
 *
 * Nine settings bound how much ink one work may carry and, until ledger I-154,
 * two of them could say so and the other seven took effect in silence. Lowering
 * one halved a picture with nothing anywhere to say which one had moved.
 *
 * Read the same way `pluginWarningsToShow` reads its warnings: empty means the
 * surface renders nothing at all, because an empty frame reads as "something
 * happened here" when nothing did.
 *
 * The lines stay in English. They are diagnostics the server wrote, and the
 * plugin warnings beside them are shown untranslated for the same reason.
 */
export function limitNotesToShow(
	result: { render_limit_notes?: string[] | null } | null | undefined
): string[] {
	return (result?.render_limit_notes ?? []).filter(
		(line) => typeof line === 'string' && line.trim() !== ''
	);
}

/**
 * The name of the limit a note is about, or null.
 *
 * Every line the server writes starts `<limit_name>: `, so the nine can be told
 * apart by a reader that only has the strings. Kept beside the reader above
 * rather than inside the page: a caller that wants to group or highlight by
 * limit should not have to re-derive the shape of the line.
 */
export function limitNoteName(line: string): string | null {
	const separator = line.indexOf(': ');
	if (separator <= 0) return null;
	const name = line.slice(0, separator);
	return /^[a-z_]+$/.test(name) ? name : null;
}
