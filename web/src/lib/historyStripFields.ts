/**
 * Which facts the history strip prints under each thumbnail.
 *
 * The strip used to print the generation and the Stage 1 model, fixed, with no
 * way to ask for anything else. Four facts are on offer now and at most two are
 * shown: the tile is only a thumbnail wide, and a third line either wraps or
 * pushes the picture out of the strip.
 *
 * None is a real answer -- a reader who wants only the pictures gets only the
 * pictures -- so an empty list is a choice and is stored as one. That is why
 * the normaliser tells an absent value (no column, an old account, a broken
 * payload) apart from an empty list: the first takes the default, the second
 * does not. Reading both through one falsy test would make "show nothing"
 * impossible to save.
 *
 * Plain .ts (no runes), so the rules are testable without the compiler -- the
 * same split $lib/uiMode.ts uses.
 */

export const HISTORY_STRIP_FIELDS = ['generation', 'model', 'engine_version', 'bytes'] as const;

export type HistoryStripField = (typeof HISTORY_STRIP_FIELDS)[number];

export function formatHistoryStripEngineVersion(value: string | null | undefined, notRecorded: string): string {
	const version = String(value ?? '').trim();
	if (!version) return notRecorded;
	return `Ver.${version.replace(/^Ver\.\s*/i, '')}`;
}

/** At most this many at once. Two lines is what the tile has room for. */
export const HISTORY_STRIP_FIELD_LIMIT = 2;

/** What the strip printed before it could be asked, so nobody's strip moves. */
export const DEFAULT_HISTORY_STRIP_FIELDS: HistoryStripField[] = ['generation', 'model'];

function isField(value: unknown): value is HistoryStripField {
	return typeof value === 'string' && (HISTORY_STRIP_FIELDS as readonly string[]).includes(value);
}

/**
 * The stored value as a list this page can print.
 *
 * Anything that is not an array is an absence and takes the default. An array
 * is taken at its word: unknown names drop out, repeats collapse, and what is
 * left is put back into the order the four are declared in, so the strip reads
 * the same whichever order they were ticked.
 */
export function normalizeHistoryStripFields(value: unknown): HistoryStripField[] {
	if (!Array.isArray(value)) return [...DEFAULT_HISTORY_STRIP_FIELDS];
	const chosen = new Set(value.filter(isField));
	return HISTORY_STRIP_FIELDS.filter((field) => chosen.has(field)).slice(0, HISTORY_STRIP_FIELD_LIMIT);
}

/** Whether a box that is not ticked can still be ticked. */
export function canAddHistoryStripField(current: readonly HistoryStripField[]): boolean {
	return current.length < HISTORY_STRIP_FIELD_LIMIT;
}

/**
 * The list after one box is clicked.
 *
 * Unticking always works. Ticking is refused once two are on -- the boxes are
 * disabled at that point, so this is the second half of the same rule rather
 * than a different one, and refusing is what keeps the reader's two choices
 * where they put them instead of silently evicting one.
 */
export function toggleHistoryStripField(
	current: readonly HistoryStripField[],
	field: HistoryStripField
): HistoryStripField[] {
	if (current.includes(field)) return current.filter((item) => item !== field);
	if (!canAddHistoryStripField(current)) return [...current];
	return normalizeHistoryStripFields([...current, field]);
}
