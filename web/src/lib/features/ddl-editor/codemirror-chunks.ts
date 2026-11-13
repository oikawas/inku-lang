import { StateEffect, StateField, type EditorState, type Text } from '@codemirror/state';
import { Decoration, EditorView, type DecorationSet } from '@codemirror/view';

// The lines of the chunk whose thing is pointed at (2026-11-13, step 1c): the
// "composition and laws" row, the drawing or the DDL itself names a thing, and
// the lines of its chunks get a background. Lines are counted from 0 in the
// DDL as shown; a line past the end is skipped.

export const chunkLinesChanged = StateEffect.define<readonly number[]>();

const chunkLine = Decoration.line({ class: 'cm-ddl-chunk-active' });

/** The line decorations for the given lines (from 0) of a document. */
export function chunkLineDecorations(doc: Text, lines: readonly number[]): DecorationSet {
	const ranges = [...new Set(lines)]
		.filter((line) => Number.isInteger(line) && line >= 0 && line < doc.lines)
		.sort((a, b) => a - b)
		.map((line) => chunkLine.range(doc.line(line + 1).from));
	return Decoration.set(ranges);
}

export const chunkLineState = StateField.define<{ lines: readonly number[]; decorations: DecorationSet }>({
	create: () => ({ lines: [], decorations: Decoration.none }),
	update(previous, tr) {
		let lines = previous.lines;
		for (const effect of tr.effects) if (effect.is(chunkLinesChanged)) lines = effect.value;
		if (lines === previous.lines && !tr.docChanged) return previous;
		return { lines, decorations: chunkLineDecorations(tr.state.doc, lines) };
	},
	provide: (field) => EditorView.decorations.from(field, (value) => value.decorations)
});

/** The line (from 0) a document position stands on. */
export function lineOf(state: EditorState, position: number): number {
	return state.doc.lineAt(position).number - 1;
}
