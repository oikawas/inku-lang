import { Compartment, EditorSelection, EditorState, Facet, StateField, Transaction, type Extension } from '@codemirror/state';
import { Decoration, EditorView, drawSelection, hoverTooltip, keymap, lineNumbers, placeholder, type DecorationSet } from '@codemirror/view';
import { defaultKeymap, history, historyKeymap, isolateHistory } from '@codemirror/commands';
import { autocompletion, completeFromList, startCompletion, type Completion, type CompletionSource } from '@codemirror/autocomplete';
import { annotate, ddlPartClass, type Part } from '../../highlight';
import { pluginDisplayName } from '../../plugin-names';
import { resolveInstructionLang } from '../../instructionLang';
import { ddlTitleName } from '../../ddl-titles';
import { SAIJIKI, saijikiWordsFor } from '../../saijiki';
import type { CompositionRange } from '../../composition-ranges';
import type { PluginEntry, PreviewForPlugin, PreviewForWord, SaijikiPreview } from './types';
import { compositionChanged, externalDdlValue, hoveredRange, numericRangeEditing, openRangeAt, rangeEditorState, rangeFocusChanged, type RangeEditorStatus } from './codemirror-ranges';
import { completionRangeTagState, completionRangeTagsChanged, type CompletionRangeLabels } from './completion-range-tags';
import type { CompletionRangeState } from './completion-range-states';
import type { PluginCall } from './plugin-calls';

const pluginCalls = Facet.define<{ source: string; calls: readonly PluginCall[] }, { source: string; calls: readonly PluginCall[] }>({ combine: values => values[0] ?? { source: '', calls: [] } });
type Token = { from: number; to: number; part: Part };

function syntaxFor(state: EditorState): { tokens: Token[]; decorations: DecorationSet } {
	let from = 0;
	const source = state.doc.toString(), answer = state.facet(pluginCalls);
	const tokens = annotate(source, answer.source === source ? answer.calls : [], true).map((part) => {
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

export function ddlEditorModel(ranges: readonly CompositionRange[], disabled = false, composing: () => boolean = () => false, answer: { source: string; calls: readonly PluginCall[] } = { source: '', calls: [] }): Extension {
	return [EditorState.lineSeparator.of('\n'), EditorState.readOnly.of(disabled), numericRangeEditing(ranges, composing),
		pluginCalls.of(answer), ddlSyntax, protectReadOnly];
}

export function replaceDdlValue(state: EditorState, value: string): Transaction | null {
	if (state.doc.toString() === value) return null;
	return state.update({ changes: { from: 0, to: state.doc.length, insert: value },
		selection: EditorSelection.cursor(Math.min(state.selection.main.head, value.length)),
		annotations: [externalDdlValue.of(true), Transaction.addToHistory.of(false)] });
}

/** A user-requested return is one undo step, unlike external synchronization. */
export function replaceDdlWithHistory(state: EditorState, value: string): Transaction | null {
	if (state.readOnly || state.field(rangeEditorState).composing || state.doc.toString() === value) return null;
	return state.update({ changes: { from: 0, to: state.doc.length, insert: value },
		selection: EditorSelection.cursor(Math.min(state.selection.main.head, value.length)),
		annotations: isolateHistory.of('full'), userEvent: 'input.discard' });
}

export function insertDdlWord(state: EditorState, word: string, append = false): Transaction | null {
	if (state.readOnly || state.field(rangeEditorState).composing) return null;
	const selection = append ? EditorSelection.cursor(state.doc.length) : state.selection.main;
	return state.update({ changes: { from: selection.from, to: selection.to, insert: word },
		selection: EditorSelection.cursor(selection.from + word.length), scrollIntoView: true, userEvent: 'input.complete' });
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
		// A title line names a chunk and draws nothing, so it offers no word (DDL 27).
		if (ddlTitleName(context.state.doc.lineAt(context.pos).text) !== null) return null;
		const settings = options();
		const prefix = context.matchBefore(/[｛{][^{}｛｝\n]*$/);
		const documentText = context.state.doc.toString();
		const lang = resolveInstructionLang(prefix ? documentText.slice(0, prefix.from) + documentText.slice(context.pos) : documentText, settings.isJapanese ? 'ja' : 'en');
		const info = (read: () => SaijikiPreview) => () => {
			const preview = read();
			settings.onPreview(preview);
			const dom = document.createElement('div');
			dom.style.whiteSpace = 'pre-line';
			dom.textContent = preview.effect + '\n' + preview.example;
			return dom;
		};
		if (prefix) {
			const needle = prefix.text.slice(1).normalize('NFKC').toLowerCase();
			const candidates: Completion[] = settings.pluginEntries.filter(entry => [...(entry.surface_ja ?? []), ...(entry.surface_en ?? [])].some(name => name.normalize('NFKC').toLowerCase().includes(needle))).map(entry => ({
				label: pluginDisplayName(entry, lang), type: 'variable', apply: (view, _completion, from, to) => {
					const inserted = pluginDisplayName(entry, lang);
					const following = view.state.sliceDoc(to, to + 1);
					view.dispatch({ changes: { from, to: to + (following === '}' || following === '｝' ? 1 : 0), insert: inserted }, selection: EditorSelection.cursor(from + inserted.length), userEvent: 'input.complete' });
				},
				detail: `${entry.word_kind === 'object' ? (settings.isJapanese ? '物の語' : 'Object') : (settings.isJapanese ? '情景の語' : 'Scene')} · ${lang === 'ja' ? entry.note_ja : entry.note_en}`,
				info: info(() => settings.previewForPlugin(entry, lang))
			}));
			return { from: prefix.from, options: candidates, filter: false };
		}
		const words: Completion[] = SAIJIKI.flatMap((category) => saijikiWordsFor(category.key, lang === 'ja').map((word, index) => ({
			label: word, type: 'keyword', info: info(() => settings.previewForWord(category.key, category.words[index] ?? word, word, lang))
		})));
		return completeFromList(words)(context);
	};
}

export type DdlEditorOptions = CompletionOptions & {
	completionSource?: string;
	completionStates?: readonly CompletionRangeState[];
	completionLabels?: CompletionRangeLabels;
	disabled: boolean;
	lineNumbers?: boolean;
	cursorAtEnd?: boolean;
	pluginCallSource?: string;
	pluginCalls?: readonly PluginCall[];
	pluginReason?: (call: PluginCall) => string;
	ranges: readonly CompositionRange[];
	label: string;
	placeholder: string;
	onChange: (value: string) => void;
	onRanges: (status: RangeEditorStatus) => void;
};

export type DdlEditorControl = {
	configure: (options: DdlEditorOptions) => void;
	setValue: (value: string) => void;
	replaceValueWithHistory: (value: string) => void;
	insertWord: (word: string) => void;
	focus: () => void;
	destroy: () => void;
};

export function pluginHoverContent(call: PluginCall, entries: PluginEntry[], language: 'ja' | 'en', previewForPlugin: PreviewForPlugin, reason: (call: PluginCall) => string): { text: string; image?: string } {
	const entry = entries.find(item => item.qualified_name === call.qualified_name);
	if (entry && call.status === 'resolved') {
		const preview = previewForPlugin(entry, language);
		return { text: `${preview.word}\n${preview.effect}\n${preview.example}`, image: preview.image };
	}
	return { text: reason(call) };
}

export function createDdlEditor(parent: HTMLElement, value: string, initial: DdlEditorOptions): DdlEditorControl {
	let options = initial;
	let view: EditorView | null = null;
	let destroyed = false;
	let pendingValue: string | null = null;
	let compositionTimer: ReturnType<typeof setTimeout> | null = null;
	let nativeCompositionTarget: EventTarget | null = null;
	let cursorPlaced = false;
	const configuration = new Compartment();
	const composing = () => view?.composing ?? false;
	const configurable = () => [ddlEditorModel(options.ranges, options.disabled, composing, { source: options.pluginCallSource ?? '', calls: options.pluginCalls ?? [] }),
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
		completionRangeTagState,
		configuration.of(configurable()), history(), keymap.of([...defaultKeymap, ...historyKeymap]),
		drawSelection(), EditorView.lineWrapping,
		hoverTooltip((view, pos) => {
			if (options.pluginCallSource !== view.state.doc.toString()) return null;
			const call = options.pluginCalls?.find(item => item.start_utf16 <= pos && pos < item.end_utf16);
			if (!call) return null;
			return { pos: call.start_utf16, end: call.end_utf16, above: true, create() {
				const dom = document.createElement('div');
				const lang = resolveInstructionLang(view.state.doc.toString(), options.isJapanese ? 'ja' : 'en');
				const content = pluginHoverContent(call, options.pluginEntries, lang, options.previewForPlugin, options.pluginReason ?? (() => ''));
				dom.textContent = content.text;
				if (content.image) { const img = document.createElement('img'); img.src = content.image; img.alt = ''; dom.appendChild(img); }
				dom.style.whiteSpace = 'pre-line'; return { dom };
			} };
		}),
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
			focus(_event, editor) { cursorPlaced = true; editor.dispatch({ effects: rangeFocusChanged.of(true) }); },
			blur(_event, editor) { editor.dispatch({ effects: rangeFocusChanged.of(false) }); }
		}),
		EditorView.updateListener.of((update) => {
			watchNativeComposition();
			if (update.docChanged && !update.state.field(rangeEditorState).composing && !update.state.readOnly) {
				let opened = false;
				update.changes.iterChanges((_fromA, _toA, _fromB, _toB, inserted) => { if (/^[{｛]$/.test(inserted.toString())) opened = true; });
				if (opened) queueMicrotask(() => { if (view) startCompletion(view); });
			}
			if (update.docChanged && !update.transactions.every((tr) => tr.annotation(externalDdlValue))) options.onChange(update.state.doc.toString());
			reportRanges();
			if ((update.docChanged || update.selectionSet) && !update.state.field(rangeEditorState).composing) {
				const position = update.state.selection.main.head;
				const token = update.state.field(ddlSyntax).tokens.find(({ from, to, part }) => from <= position && position <= to && part.kind !== 'plain');
				const lang = resolveInstructionLang(update.state.doc.toString(), options.isJapanese ? 'ja' : 'en');
				if (token?.part.kind === 'plugin-name' && token.part.known) {
					const call = options.pluginCalls?.find(item => item.start_utf16 === token.from && item.end_utf16 === token.to);
					const entry = options.pluginEntries.find((entry) => entry.qualified_name === call?.qualified_name);
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
			if (view && (previous.disabled !== next.disabled || previous.pluginCalls !== next.pluginCalls || previous.pluginCallSource !== next.pluginCallSource || previous.ranges !== next.ranges
				|| previous.label !== next.label || previous.placeholder !== next.placeholder || previous.lineNumbers !== next.lineNumbers)) view.dispatch({ effects: configuration.reconfigure(configurable()) });
			if (view && next.completionLabels && (previous.completionSource !== next.completionSource || previous.completionStates !== next.completionStates || previous.completionLabels !== next.completionLabels)) {
				view.dispatch({ effects: completionRangeTagsChanged.of({ source: next.completionSource ?? '', ranges: next.completionStates ?? [], labels: next.completionLabels }) });
			}
		},
		setValue(next) {
			if (!view || view.state.doc.toString() === next) return;
			if (view.composing || view.state.field(rangeEditorState).composing) { pendingValue = next; return; }
			const tr = replaceDdlValue(view.state, next);
			if (tr) view.dispatch(tr);
		},
		replaceValueWithHistory(next) {
			if (!view || view.composing) return;
			const tr = replaceDdlWithHistory(view.state, next);
			if (tr) { view.dispatch(tr); view.focus(); }
		},
		insertWord(word) {
			if (!view) return;
			const tr = insertDdlWord(view.state, word, options.cursorAtEnd === true && !cursorPlaced);
			if (tr) { view.dispatch(tr); view.focus(); }
		},
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
