import { Compartment, EditorSelection, EditorState, Facet, StateField, Transaction, type Extension } from '@codemirror/state';
import { Decoration, EditorView, drawSelection, keymap, lineNumbers, placeholder, type DecorationSet } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap } from '@codemirror/commands';
import { autocompletion, completeFromList, type Completion, type CompletionSource } from '@codemirror/autocomplete';
import { annotate, ddlPartClass, type Part } from '../../highlight';
import { pluginDisplayName, type PluginNameIndex } from '../../plugin-names';
import { resolveInstructionLang } from '../../instructionLang';
import { SAIJIKI, saijikiWordsFor } from '../../saijiki';
import type { CompositionRange } from '../../composition-ranges';
import type { PluginEntry, PreviewForPlugin, PreviewForWord, SaijikiPreview } from './types';
import { compositionChanged, externalDdlValue, hoveredRange, numericRangeEditing, openRangeAt, rangeEditorState, rangeFocusChanged, type RangeEditorStatus } from './codemirror-ranges';

const pluginNames = Facet.define<PluginNameIndex, PluginNameIndex>({ combine: (values) => values[0] ?? { names: [], firesOn: [] } });
type Token = { from: number; to: number; part: Part };

function syntaxFor(state: EditorState): { tokens: Token[]; decorations: DecorationSet } {
	let from = 0;
	const tokens = annotate(state.doc.toString(), state.facet(pluginNames)).map((part) => {
		const token = { from, to: from + part.text.length, part };
		from = token.to;
		return token;
	});
	const decorations = tokens.flatMap(({ from, to, part }) => {
		const cls = ddlPartClass(part);
		return cls ? [Decoration.mark({ class: cls }).range(from, to)] : [];
	});
	return { tokens, decorations: Decoration.set(decorations, true) };
}

/** No second text layer: decorate the actual editable document. */
export const ddlSyntax = StateField.define<{ tokens: Token[]; decorations: DecorationSet }>({
	create: syntaxFor,
	update(previous, tr) {
		if (tr.state.field(rangeEditorState).composing) {
			return { decorations: previous.decorations.map(tr.changes),
				tokens: previous.tokens.map((token) => ({ ...token, from: tr.changes.mapPos(token.from, -1), to: tr.changes.mapPos(token.to) })) };
		}
		return tr.docChanged || tr.reconfigured || tr.startState.field(rangeEditorState).composing ? syntaxFor(tr.state) : previous;
	},
	provide: (field) => EditorView.decorations.from(field, (value) => value.decorations)
});

const protectReadOnly = EditorState.transactionFilter.of((tr) => tr.startState.readOnly && tr.docChanged && !tr.annotation(externalDdlValue) ? [] : tr);

export function ddlEditorModel(ranges: readonly CompositionRange[], names: PluginNameIndex, disabled = false, composing: () => boolean = () => false): Extension {
	return [EditorState.lineSeparator.of('\n'), EditorState.readOnly.of(disabled), numericRangeEditing(ranges, composing),
		pluginNames.of(names), ddlSyntax, protectReadOnly];
}

export function replaceDdlValue(state: EditorState, value: string): Transaction | null {
	if (state.doc.toString() === value) return null;
	return state.update({ changes: { from: 0, to: state.doc.length, insert: value },
		selection: EditorSelection.cursor(Math.min(state.selection.main.head, value.length)),
		annotations: [externalDdlValue.of(true), Transaction.addToHistory.of(false)] });
}

export function insertDdlWord(state: EditorState, word: string): Transaction | null {
	if (state.readOnly || state.field(rangeEditorState).composing) return null;
	return state.update({ changes: { from: state.selection.main.from, to: state.selection.main.to, insert: word },
		selection: EditorSelection.cursor(state.selection.main.from + word.length), scrollIntoView: true, userEvent: 'input.complete' });
}

type CompletionOptions = {
	isJapanese: boolean;
	pluginEntries: PluginEntry[];
	previewForWord: PreviewForWord;
	previewForPlugin: PreviewForPlugin;
	onPreview: (preview: SaijikiPreview) => void;
};

/** Use the same live vocabulary and language rule as the editor's word panel. */
export function ddlCompletions(options: () => CompletionOptions): CompletionSource {
	return (context) => {
		if (context.state.readOnly || context.state.field(rangeEditorState).composing) return null;
		const active = context.state.field(rangeEditorState).active;
		if (active && context.pos >= active.bodyStart && context.pos <= active.bodyEnd) return null;
		const settings = options();
		const lang = resolveInstructionLang(context.state.doc.toString(), settings.isJapanese ? 'ja' : 'en');
		const info = (read: () => SaijikiPreview) => () => {
			const preview = read();
			settings.onPreview(preview);
			const dom = document.createElement('div');
			dom.style.whiteSpace = 'pre-line';
			dom.textContent = preview.effect + '\n' + preview.example;
			return dom;
		};
		const words: Completion[] = SAIJIKI.flatMap((category) => saijikiWordsFor(category.key, lang === 'ja').map((word, index) => ({
			label: word, type: 'keyword', info: info(() => settings.previewForWord(category.key, category.words[index] ?? word, word, lang))
		})));
		for (const entry of settings.pluginEntries) words.push({ label: pluginDisplayName(entry, lang), type: 'variable', info: info(() => settings.previewForPlugin(entry, lang)) });
		return completeFromList(words)(context);
	};
}

export type DdlEditorOptions = CompletionOptions & {
	disabled: boolean;
	lineNumbers?: boolean;
	cursorAtEnd?: boolean;
	pluginNameIndex: PluginNameIndex;
	ranges: readonly CompositionRange[];
	label: string;
	placeholder: string;
	onChange: (value: string) => void;
	onRanges: (status: RangeEditorStatus) => void;
};

export type DdlEditorControl = {
	configure: (options: DdlEditorOptions) => void;
	setValue: (value: string) => void;
	insertWord: (word: string) => void;
	focus: () => void;
	destroy: () => void;
};

export function createDdlEditor(parent: HTMLElement, value: string, initial: DdlEditorOptions): DdlEditorControl {
	let options = initial;
	let view: EditorView | null = null;
	let destroyed = false;
	let pendingValue: string | null = null;
	let compositionTimer: ReturnType<typeof setTimeout> | null = null;
	let nativeCompositionTarget: EventTarget | null = null;
	const configuration = new Compartment();
	const composing = () => view?.composing ?? false;
	const configurable = () => [ddlEditorModel(options.ranges, options.pluginNameIndex, options.disabled, composing),
		EditorView.editable.of(!options.disabled), EditorView.contentAttributes.of({ 'aria-label': options.label, spellcheck: 'false', tabindex: options.disabled ? '-1' : '0' }),
		placeholder(options.placeholder), options.lineNumbers === false ? [] : lineNumbers()];
	const reportRanges = () => {
		if (!view) return;
		const { preview, invalid, composing } = view.state.field(rangeEditorState);
		options.onRanges({ preview, invalid, composing });
	};
	const beginComposition = () => {
		if (compositionTimer !== null) clearTimeout(compositionTimer);
		compositionTimer = null;
		view?.dispatch({ effects: compositionChanged.of(true) });
	};
	const finishComposition = () => {
		compositionTimer = null;
		if (!view || destroyed) return;
		// Native CodeMirror input can finish after the DOM's end event. Wait for
		// its public composing flag; never change the preedit document or DOM.
		if (view.composing) { compositionTimer = setTimeout(finishComposition, 20); return; }
		view.dispatch({ effects: compositionChanged.of(false) });
		if (pendingValue !== null) {
			const next = pendingValue;
			pendingValue = null;
			const tr = replaceDdlValue(view.state, next);
			if (tr) view.dispatch(tr);
		}
	};
	const endComposition = () => { if (compositionTimer !== null) clearTimeout(compositionTimer); compositionTimer = setTimeout(finishComposition, 0); };
	function watchNativeComposition(): void {
		// Chromium may send composition events to EditContext instead of DOM.
		const next = (view?.contentDOM as (HTMLElement & { editContext?: EventTarget | null }) | undefined)?.editContext ?? null;
		if (next === nativeCompositionTarget) return;
		nativeCompositionTarget?.removeEventListener('compositionstart', beginComposition);
		nativeCompositionTarget?.removeEventListener('compositionend', endComposition);
		nativeCompositionTarget = next;
		next?.addEventListener('compositionstart', beginComposition);
		next?.addEventListener('compositionend', endComposition);
	}
	view = new EditorView({ parent, state: EditorState.create({ doc: value,
		selection: initial.cursorAtEnd ? EditorSelection.cursor(value.length) : undefined,
		extensions: [
		configuration.of(configurable()), history(), keymap.of([...defaultKeymap, ...historyKeymap]),
		drawSelection(), EditorView.lineWrapping,
		autocompletion({ override: [ddlCompletions(() => options)] }),
		EditorView.domEventHandlers({
			mousedown(event, editor) {
				const label = event.target instanceof Element ? event.target.closest<HTMLElement>('[data-ddl-range]') : null;
				if (!label || options.disabled) return false;
				const tr = openRangeAt(editor.state, Number(label.dataset.ddlRange));
				if (!tr) return false;
				event.preventDefault(); editor.dispatch(tr); editor.focus(); return true;
			},
			mousemove(event, editor) {
				const label = event.target instanceof Element ? event.target.closest<HTMLElement>('[data-ddl-range]') : null;
				const start = label ? Number(label.dataset.ddlRange) : null;
				if (editor.state.field(rangeEditorState).hover !== start) editor.dispatch({ effects: hoveredRange.of(start) });
			},
			mouseleave(_event, editor) { if (editor.state.field(rangeEditorState).hover !== null) editor.dispatch({ effects: hoveredRange.of(null) }); },
			focus(_event, editor) { editor.dispatch({ effects: rangeFocusChanged.of(true) }); },
			blur(_event, editor) { editor.dispatch({ effects: rangeFocusChanged.of(false) }); }
		}),
		EditorView.updateListener.of((update) => {
			watchNativeComposition();
			if (update.docChanged && !update.transactions.every((tr) => tr.annotation(externalDdlValue))) options.onChange(update.state.doc.toString());
			reportRanges();
			if ((update.docChanged || update.selectionSet) && !update.state.field(rangeEditorState).composing) {
				const position = update.state.selection.main.head;
				const token = update.state.field(ddlSyntax).tokens.find(({ from, to, part }) => from <= position && position <= to && part.kind !== 'plain');
				const lang = resolveInstructionLang(update.state.doc.toString(), options.isJapanese ? 'ja' : 'en');
				if (token?.part.kind === 'plugin-name' && token.part.known) {
					const entry = options.pluginEntries.find((entry) => entry.qualified_name === token.part.text || entry.aliases?.includes(token.part.text));
					if (entry) options.onPreview(options.previewForPlugin(entry, lang));
				} else if (token?.part.kind === 'saijiki' && token.part.categoryKey) {
					const category = SAIJIKI.find((entry) => entry.key === token.part.categoryKey);
					const index = saijikiWordsFor(token.part.categoryKey, lang === 'ja').findIndex((word) => word.toLowerCase() === token.part.text.toLowerCase());
					options.onPreview(options.previewForWord(token.part.categoryKey, category?.words[index] ?? token.part.text, token.part.text, lang));
				}
			}
		})
	] }) });
	view.contentDOM.addEventListener('compositionstart', beginComposition);
	view.contentDOM.addEventListener('compositionend', endComposition);
	watchNativeComposition();
	view.dispatch({ effects: rangeFocusChanged.of(view.hasFocus) });
	reportRanges();
	return {
		configure(next) {
			const previous = options;
			options = next;
			if (view && (previous.disabled !== next.disabled || previous.pluginNameIndex !== next.pluginNameIndex || previous.ranges !== next.ranges
				|| previous.label !== next.label || previous.placeholder !== next.placeholder || previous.lineNumbers !== next.lineNumbers)) view.dispatch({ effects: configuration.reconfigure(configurable()) });
		},
		setValue(next) {
			if (!view || view.state.doc.toString() === next) return;
			if (view.composing || view.state.field(rangeEditorState).composing) { pendingValue = next; return; }
			const tr = replaceDdlValue(view.state, next);
			if (tr) view.dispatch(tr);
		},
		insertWord(word) { if (view) { const tr = insertDdlWord(view.state, word); if (tr) { view.dispatch(tr); view.focus(); } } },
		focus() { view?.focus(); },
		destroy() {
			destroyed = true;
			if (compositionTimer !== null) clearTimeout(compositionTimer);
			nativeCompositionTarget?.removeEventListener('compositionstart', beginComposition);
			nativeCompositionTarget?.removeEventListener('compositionend', endComposition);
			view?.contentDOM.removeEventListener('compositionstart', beginComposition);
			view?.contentDOM.removeEventListener('compositionend', endComposition);
			view?.destroy(); view = null;
		}
	};
}
