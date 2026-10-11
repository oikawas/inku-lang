import { StateEffect, StateField } from '@codemirror/state';
import { Decoration, EditorView, WidgetType, type DecorationSet } from '@codemirror/view';
import type { CompletionRangeState } from './completion-range-states';

export type CompletionRangeLabels = Record<CompletionRangeState['state'], string>;
class CompletionRangeTag extends WidgetType {
	readonly label: string;
	readonly state: CompletionRangeState['state'];
	constructor(label: string, state: CompletionRangeState['state']) { super(); this.label = label; this.state = state; }
	eq(other: CompletionRangeTag): boolean { return this.label === other.label && this.state === other.state; }
	toDOM(): HTMLElement {
		const tag = document.createElement('span');
		tag.className = 'cm-ddl-completion-tag';
		tag.dataset.completionState = this.state;
		tag.textContent = this.label;
		return tag;
	}
}

/** Core supplies UTF-16 positions. Tags are decorations, never source edits. */
type CompletionRangeTags = { source: string; ranges: readonly CompletionRangeState[]; labels: CompletionRangeLabels };
export const completionRangeTagsChanged = StateEffect.define<CompletionRangeTags>();

function decorations(doc: string, { source, ranges, labels }: CompletionRangeTags): DecorationSet {
	return doc !== source ? Decoration.none : Decoration.set(ranges.flatMap((range) => {
		if (!Number.isInteger(range.utf16_start) || !Number.isInteger(range.utf16_end)
			|| range.utf16_start < 0 || range.utf16_start >= range.utf16_end || range.utf16_end > doc.length || !labels[range.state]) return [];
		return [Decoration.widget({ widget: new CompletionRangeTag(labels[range.state], range.state), side: 1 }).range(range.utf16_end)];
	}), true);
}

// A separate effect updates these tags without reconfiguring numeric editing.
export const completionRangeTagState = StateField.define<{ source: string; decorations: DecorationSet }>({
	create: () => ({ source: '', decorations: Decoration.none }),
	update(previous, tr) {
		for (const effect of tr.effects) if (effect.is(completionRangeTagsChanged)) {
			return { source: effect.value.source, decorations: decorations(tr.newDoc.toString(), effect.value) };
		}
		return tr.docChanged ? { source: tr.newDoc.toString(), decorations: Decoration.none } : previous;
	},
	provide: (field) => EditorView.decorations.from(field, (value) => value.decorations),
});
