import { Annotation, EditorSelection, EditorState, Facet, StateEffect, StateField, type Extension, type SelectionRange, type Transaction } from '@codemirror/state';
import { Decoration, EditorView, type DecorationSet } from '@codemirror/view';
import { editNumericRange, matchingRange, rangePreview, scanNumericRanges, type CompositionRange, type NumericRange, type RangePreview } from '../../composition-ranges';

export const rangeTable = Facet.define<readonly CompositionRange[], readonly CompositionRange[]>({ combine: (values) => values[0] ?? [] });
export const compositionGuard = Facet.define<() => boolean, () => boolean>({ combine: (values) => values[0] ?? (() => false) });
export const compositionChanged = StateEffect.define<boolean>();
export const rangeFocusChanged = StateEffect.define<boolean>();
export const hoveredRange = StateEffect.define<number | null>();
export const externalDdlValue = Annotation.define<boolean>();

export type RangeEditorStatus = { preview: RangePreview | null; invalid: boolean; composing: boolean };
export type RangeEditorState = RangeEditorStatus & {
	ranges: NumericRange[];
	active: NumericRange | null;
	pendingName: boolean;
	hover: number | null;
	focused: boolean;
	decorations: DecorationSet;
	atomic: DecorationSet;
};

function contains(range: NumericRange, selection: SelectionRange): boolean {
	return selection.empty
		? selection.head > range.start && selection.head < range.end
		: selection.from < range.end && selection.to > range.start;
}

function mappedRange(range: NumericRange, tr: Transaction): NumericRange {
	const map = (position: number, side = 1) => tr.changes.mapPos(position, side);
	return { ...range, start: map(range.start, -1), end: map(range.end), nameStart: map(range.nameStart, -1), nameEnd: map(range.nameEnd),
		bodyStart: map(range.bodyStart, -1), bodyEnd: map(range.bodyEnd) };
}

function isComposing(tr: Transaction, previous: RangeEditorState): boolean {
	let composing = previous.composing;
	for (const effect of tr.effects) if (effect.is(compositionChanged)) composing = effect.value;
	return composing || tr.startState.facet(compositionGuard)();
}

function pendingNameAfter(previous: RangeEditorState, tr: Transaction): boolean {
	if (!previous.active || tr.reconfigured || tr.annotation(externalDdlValue) || tr.isUserEvent('undo') || tr.isUserEvent('redo')) return false;
	if (!tr.docChanged || tr.startState.doc.eq(tr.newDoc)) return previous.pendingName;
	const range = previous.active;
	let wordsEdited = false;
	let numbersEdited = false;
	tr.changes.iterChangedRanges((from, to) => {
		const touches = (start: number, end: number, includeEnd = false) => from === to
			? from >= start && (from < end || (includeEnd && from === end))
			: from < end && to > start;
		wordsEdited ||= touches(range.nameStart, range.nameEnd);
		numbersEdited ||= touches(range.bodyStart, range.bodyEnd, true);
	});
	return wordsEdited ? false : previous.pendingName || numbersEdited;
}

function decorationsFor(ranges: NumericRange[], state: EditorState, focused: boolean): { decorations: DecorationSet; atomic: DecorationSet } {
	const visible = [];
	const hidden = [];
	for (const range of ranges) {
		if (!matchingRange(range, [...state.facet(rangeTable)])) continue;
		const rawName = state.doc.sliceString(range.nameStart, range.nameEnd);
		const labelStart = range.nameStart + rawName.lastIndexOf(range.name);
		visible.push(Decoration.mark({ class: 'cm-ddl-range-name', attributes: { 'data-ddl-range': String(range.start) } }).range(labelStart, labelStart + range.name.length));
		if (focused && state.selection.ranges.some((selection) => contains(range, selection))) continue;
		hidden.push(Decoration.replace({}).range(range.nameEnd, range.end));
		const legacy = /^(?:［構図］|\[composition\])\s*/.exec(rawName);
		if (legacy) hidden.push(Decoration.replace({}).range(range.nameStart, range.nameStart + legacy[0].length));
	}
	return { decorations: Decoration.set([...visible, ...hidden], true), atomic: Decoration.set(hidden, true) };
}

function derive(state: EditorState, ranges: NumericRange[], previous: RangeEditorState | null, focused: boolean, hover: number | null): RangeEditorState {
	const active = focused ? ranges.find((range) => contains(range, state.selection.main)) ?? null : null;
	const pendingName = !!active && !!previous && previous.active?.start === active.start && previous.pendingName;
	const shown = active ?? ranges.find((range) => range.start === hover) ?? null;
	let preview: RangePreview | null = null;
	if (shown?.bounds) preview = rangePreview(shown.bounds);
	else if (shown && previous?.active?.start === shown.start && previous.preview) preview = { ...previous.preview, invalid: true };
	return { ranges, active, pendingName, hover, focused, preview, invalid: ranges.some((range) => range.bounds === null), composing: false,
		...decorationsFor(ranges, state, focused) };
}

/** Document ranges are cached; cursor movement only changes their decorations. */
export const rangeEditorState = StateField.define<RangeEditorState>({
	create(state) { return derive(state, scanNumericRanges(state.doc.toString()), null, true, null); },
	update(previous, tr) {
		let focused = previous.focused;
		let hover = previous.hover === null ? null : tr.changes.mapPos(previous.hover, -1);
		for (const effect of tr.effects) {
			if (effect.is(rangeFocusChanged)) focused = effect.value;
			if (effect.is(hoveredRange)) hover = effect.value;
		}
		const pendingName = pendingNameAfter(previous, tr);
		if (isComposing(tr, previous) && !tr.annotation(externalDdlValue)) {
			return { ...previous, focused, hover, pendingName, composing: true,
				ranges: previous.ranges.map((range) => mappedRange(range, tr)),
				active: previous.active ? mappedRange(previous.active, tr) : null,
				decorations: previous.decorations.map(tr.changes), atomic: previous.atomic.map(tr.changes) };
		}
		const reset = tr.annotation(externalDdlValue);
		const ranges = tr.docChanged || tr.reconfigured || previous.composing || reset
			? scanNumericRanges(tr.newDoc.toString()) : previous.ranges;
		const mapped = reset ? null : { ...previous, pendingName, active: previous.active ? mappedRange(previous.active, tr) : null };
		let next = derive(tr.state, ranges, mapped, focused, reset ? null : hover);
		// A temporarily broken axis or parenthesis remains an invalid edit until
		// the caret leaves it. Keep its last valid frame, never invent bounds.
		if (!next.active && mapped?.active && focused && mapped.active.end > mapped.active.start && contains(mapped.active, tr.newSelection.main)) {
			next = { ...next, active: { ...mapped.active, bounds: null }, pendingName: mapped.pendingName, invalid: true,
				preview: mapped.preview ? { ...mapped.preview, invalid: true } : null };
		}
		return next;
	},
	provide: (field) => [EditorView.decorations.from(field, (value) => value.decorations),
		EditorView.atomicRanges.of((view) => view.state.field(field).atomic)]
});

/** Follow names in the same transaction that leaves a numeric edit. */
const followNameOnLeaving = EditorState.transactionFilter.of((tr) => {
	const previous = tr.startState.field(rangeEditorState);
	if (!previous.active || tr.startState.readOnly || tr.reconfigured || tr.annotation(externalDdlValue)
		|| tr.isUserEvent('undo') || tr.isUserEvent('redo') || isComposing(tr, previous)) return tr;
	let focused = previous.focused;
	for (const effect of tr.effects) if (effect.is(rangeFocusChanged)) focused = effect.value;
	const start = tr.changes.mapPos(previous.active.start, -1);
	const source = tr.newDoc.toString();
	const range = scanNumericRanges(source).find((range) => range.start === start);
	if (!range?.bounds || !pendingNameAfter(previous, tr) || (focused && contains(range, tr.newSelection.main))) return tr;
	const edited = editNumericRange(source, range, range.body, [...tr.startState.facet(rangeTable)]);
	const name = edited.source.slice(edited.range.nameStart, edited.range.nameEnd);
	if (name === source.slice(range.nameStart, range.nameEnd)) return tr;
	return [tr, { changes: { from: range.nameStart, to: range.nameEnd, insert: name }, sequential: true }];
});

export function numericRangeEditing(table: readonly CompositionRange[], composing: () => boolean = () => false): Extension {
	return [rangeTable.of(table), compositionGuard.of(composing), rangeEditorState, followNameOnLeaving];
}

/** Clicking the place opens its ordinary source text, not another input. */
export function openRangeAt(state: EditorState, start: number): ReturnType<EditorState['update']> | null {
	const range = state.field(rangeEditorState).ranges.find((range) => range.start === start);
	return range ? state.update({ selection: EditorSelection.cursor(range.bodyStart), effects: rangeFocusChanged.of(true), scrollIntoView: true }) : null;
}
