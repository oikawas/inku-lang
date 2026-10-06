import { editNumericRange, rangePreview, scanNumericRanges, type CompositionRange, type NumericRange, type RangePreview } from './composition-ranges';

export function createRangeEditState(deps: {
	source: () => string; ranges: () => CompositionRange[]; disabled: () => boolean;
	change: (source: string) => void; preview: (preview: RangePreview | null) => void; invalid: (invalid: boolean) => void;
}) {
	let active = $state<{ range: NumericRange; source: string; openedName: string; lastValid: RangePreview | null } | null>(null);
	const invalidEdits = new Set<string>();
	function sync(source = deps.source()): void {
		for (const edited of invalidEdits) if (!source.includes(edited)) invalidEdits.delete(edited);
		deps.invalid(invalidEdits.size > 0 || scanNumericRanges(source).some((range) => !range.bounds));
	}
	function reset(forgetEdits = false): void {
		active = null;
		if (forgetEdits) invalidEdits.clear();
		deps.preview(null);
		sync();
	}
	function show(range: NumericRange): void {
		const preview = range.bounds ? rangePreview(range.bounds) : active?.lastValid ?? null;
		deps.preview(preview ? { ...preview, invalid: !range.bounds } : null);
	}
	function open(range: NumericRange): void {
		show(range);
		sync();
		if (!deps.disabled()) active = { range, source: deps.source(), openedName: range.name, lastValid: range.bounds ? rangePreview(range.bounds) : null };
	}
	function edit(body: string): void {
		if (!active || deps.disabled()) return;
		const next = editNumericRange(deps.source(), active.range, body, deps.ranges(), active.openedName);
		invalidEdits.delete(deps.source().slice(active.range.start, active.range.end));
		if (!next.range.bounds) invalidEdits.add(next.source.slice(next.range.start, next.range.end));
		const preview = next.range.bounds ? rangePreview(next.range.bounds) : active.lastValid;
		active = { ...next, openedName: active.openedName, lastValid: preview };
		sync(next.source);
		deps.preview(preview ? { ...preview, invalid: !next.range.bounds } : null);
		deps.change(next.source);
	}
	return { get active() { return active; }, reset, sync, show, open, edit };
}
