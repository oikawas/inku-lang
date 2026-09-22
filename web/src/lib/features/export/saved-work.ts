export type SavedWorkExportScopeKind = 'current' | 'selection' | 'lineage-path';

export type SavedWorkExportItem = {
	id: string;
	at: number;
	preview?: string | null;
	description?: string | null;
	trashed?: boolean;
	unavailable?: boolean;
};

export type SavedWorkExportScope = {
	kind: SavedWorkExportScopeKind;
	works: readonly SavedWorkExportItem[];
	/** A caller may name a path or another scoped set more specifically. */
	description?: string | null;
};

export type SavedWorkExportSnapshot = {
	kind: SavedWorkExportScopeKind;
	ids: string[];
	works: SavedWorkExportItem[];
	description: string | null;
};

function chronological(left: SavedWorkExportItem, right: SavedWorkExportItem): number {
	return left.at - right.at || left.id.localeCompare(right.id);
}

/**
 * Freeze one export target at the menu boundary. Checked work is chronological;
 * a lineage path is already a meaningful ancestor-to-descendant sequence.
 */
export function snapshotSavedWorkExport(scope: SavedWorkExportScope | null | undefined): SavedWorkExportSnapshot | null {
	if (!scope) return null;
	const seen = new Set<string>();
	for (const work of scope.works) {
		// A snapshot names one exact export. Omitting a target here would silently
		// change a checked set or a lineage sequence into a different export.
		if (!work.id || work.trashed || work.unavailable || seen.has(work.id)) return null;
		seen.add(work.id);
	}
	if (scope.works.length === 0) return null;
	const works = scope.kind === 'lineage-path' ? [...scope.works] : [...scope.works].sort(chronological);
	return {
		kind: scope.kind,
		ids: works.map((work) => work.id),
		works,
		description: scope.description ?? null,
	};
}
