/**
 * Namespaced plugin references in DDL text: which ones exist, and what a
 * wrong one would have fired.
 *
 * The expansion layer strips a reference whose qualified name it does not
 * know, and the sentence around it goes with it -- a request for twenty
 * blades of grass can leave one line on the paper. The warning reaches the
 * record, never the writer. This module gives the editor what it needs to
 * say so while the name is being typed.
 *
 * The server is the authority on what counts as a reference: the pattern
 * below is the same one the expansion layer scans with
 * (`_PLUGIN_REFERENCE_RE`, server/src/inku_server/plugins/document_format.py).
 * Copying the pattern, not just the idea, keeps the two judgements equal:
 * whatever the editor marks is exactly what the server would strip.
 */

/** Same source as document_format.py:60. Global so a scan can resume mid-run. */
const REFERENCE_RE = /(?<![A-Za-z0-9_])[A-Z][A-Za-z0-9_-]*\.[^\s、。,;:]+/g;

export type PluginNameEntry = {
	qualified_name: string;
	fires_on_ja?: string[];
	fires_on_en?: string[];
};

export type PluginNameIndex = {
	/** Qualified names that exist on this server, longest first. */
	names: string[];
	/** Firing phrases, longest first, each with the entry word it belongs to. */
	firesOn: { phrase: string; word: string }[];
};

export type PluginReference = {
	start: number;
	end: number;
	text: string;
	/** True when the server holds this qualified name. */
	known: boolean;
};

/** The part after the namespace: `Nature.下草` -> `下草`. */
function localPart(qualifiedName: string): string {
	const dot = qualifiedName.indexOf('.');
	return dot < 0 ? qualifiedName : qualifiedName.slice(dot + 1);
}

/** The part before the namespace: `Nature.下草` -> `Nature`. */
export function namespacePart(qualifiedName: string): string {
	const dot = qualifiedName.indexOf('.');
	return dot < 0 ? '' : qualifiedName.slice(0, dot);
}

export function buildPluginNameIndex(entries: PluginNameEntry[] | undefined | null): PluginNameIndex {
	const names: string[] = [];
	const firesOn: { phrase: string; word: string }[] = [];
	for (const entry of entries ?? []) {
		const qualified = entry?.qualified_name;
		if (!qualified) continue;
		names.push(qualified);
		const word = localPart(qualified);
		for (const phrase of [...(entry.fires_on_ja ?? []), ...(entry.fires_on_en ?? [])]) {
			const trimmed = phrase?.trim();
			if (trimmed) firesOn.push({ phrase: trimmed, word });
		}
	}
	// Longest first on both lists: `Nature.下草` must win over a shorter name
	// that happens to be its prefix, and `枯れ草` over `枯草`.
	names.sort((a, b) => b.length - a.length);
	firesOn.sort((a, b) => b.phrase.length - a.phrase.length);
	return { names, firesOn };
}

/** The known qualified name this text starts with, or null. */
function knownPrefix(text: string, index: PluginNameIndex): string | null {
	for (const name of index.names) {
		if (text.startsWith(name)) return name;
	}
	return null;
}

/**
 * Every namespaced reference in `text`, in order and non-overlapping.
 *
 * A known name ends the reference where the name ends, because that is where
 * the expansion layer ends it too: `Nature.下草と菖蒲` expands the name and
 * leaves `と菖蒲` as ordinary text. What follows is scanned again, so a bad
 * reference sitting behind a good one is still found.
 */
export function scanPluginReferences(text: string, index: PluginNameIndex): PluginReference[] {
	const found: PluginReference[] = [];
	let at = 0;
	while (at < text.length) {
		REFERENCE_RE.lastIndex = at;
		const match = REFERENCE_RE.exec(text);
		if (!match) break;
		const start = match.index;
		const known = knownPrefix(match[0], index);
		const end = known === null ? start + match[0].length : start + known.length;
		found.push({ start, end, text: text.slice(start, end), known: known !== null });
		at = end;
	}
	return found;
}

/**
 * For a reference the server does not know, the entry word its local part
 * would have fired as plain text -- `Nature.菖蒲` -> `下草`. Null when no
 * entry claims the word, which is the difference between a name written
 * wrongly and a name that does not exist at all.
 */
export function firingWordFor(reference: string, index: PluginNameIndex): string | null {
	const local = localPart(reference);
	if (!local) return null;
	const lowered = local.toLowerCase();
	for (const { phrase, word } of index.firesOn) {
		if (local.startsWith(phrase) || lowered.startsWith(phrase.toLowerCase())) return word;
	}
	return null;
}

export type UnknownPluginName = {
	/** The reference as written, e.g. `Nature.菖蒲`. */
	text: string;
	/** Its namespace, e.g. `Nature`. */
	namespace: string;
	/** The word it would fire as without the namespace, or null. */
	firesAs: string | null;
};

/**
 * The expansion warnings a finished drawing should show.
 *
 * Empty means the surface renders nothing at all -- an empty frame reads as
 * "something happened here" when nothing did.
 */
export function pluginWarningsToShow(
	result: { plugin_warnings?: string[] | null } | null | undefined
): string[] {
	return (result?.plugin_warnings ?? []).filter(
		(line) => typeof line === 'string' && line.trim() !== ''
	);
}

/** The unknown references in `text`, deduplicated, in first-seen order. */
export function unknownPluginNames(text: string, index: PluginNameIndex): UnknownPluginName[] {
	const seen = new Set<string>();
	const unknown: UnknownPluginName[] = [];
	for (const reference of scanPluginReferences(text, index)) {
		if (reference.known || seen.has(reference.text)) continue;
		seen.add(reference.text);
		unknown.push({
			text: reference.text,
			namespace: namespacePart(reference.text),
			firesAs: firingWordFor(reference.text, index)
		});
	}
	return unknown;
}
