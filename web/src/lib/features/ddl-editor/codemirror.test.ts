import assert from 'node:assert/strict';
import test from 'node:test';
import { EditorSelection, EditorState } from '@codemirror/state';
import { history, undo } from '@codemirror/commands';
import { CompletionContext } from '@codemirror/autocomplete';
import { readCompositionRanges, scanNumericRanges } from '../../composition-ranges.ts';
import { buildPluginNameIndex, unknownPluginNames } from '../../plugin-names.ts';
import { ddlPartClass, highlightDDL } from '../../highlight.ts';
import { ddlCompletions, ddlEditorModel, ddlSyntax, insertDdlWord, replaceDdlValue } from './codemirror.ts';
import { compositionChanged, openRangeAt, rangeEditorState, rangeFocusChanged } from './codemirror-ranges.ts';

const ranges = readCompositionRanges({ schema: 'inku.composition-ranges.v1', ranges: [
	{ key: 'left', words: { ja: '左上', en: 'top left' }, bounds: [[0, 1], [0, 1], [1, 3], [1, 3]], corner: false },
	{ key: 'right', words: { ja: '右下', en: 'bottom right' }, bounds: [[2, 3], [2, 3], [1, 1], [1, 1]], corner: false }
] });
const names = buildPluginNameIndex([{ qualified_name: 'Nature.Grass', aliases: ['Nature.下草'], fires_on_ja: ['草'] }]);
const source = '  紙。\r\n［構図］右下（横2/3〜1、縦2/3〜1）に、赤い円。\n青い線。  ';
function editor(doc = source, disabled = false, table = ranges) {
	return EditorState.create({ doc, selection: { anchor: doc.length }, extensions: [ddlEditorModel(table, names, disabled), history()] });
}
function hidden(state: EditorState): [number, number][] {
	const replacements: [number, number][] = [];
	state.field(rangeEditorState).atomic.between(0, state.doc.length, (from, to) => replacements.push([from, to]));
	return replacements;
}
function displayed(state: EditorState): string {
	return hidden(state).reverse().reduce((text, [from, to]) => text.slice(0, from) + text.slice(to), state.doc.toString());
}
function open(state: EditorState): EditorState {
	return openRangeAt(state, scanNumericRanges(state.doc.toString())[0].start)!.state;
}
function changeBody(state: EditorState, body: string): EditorState {
	const range = state.field(rangeEditorState).active!;
	return state.update({ changes: { from: range.bodyStart, to: range.bodyEnd, insert: body },
		selection: { anchor: range.bodyStart + body.length }, userEvent: 'input' }).state;
}

test('the real replacement decorations fold exact named ranges and retain complete copy/save source', () => {
	const state = editor();
	assert.equal(displayed(state), '  紙。\r\n右下に、赤い円。\n青い線。  ');
	assert.equal(state.doc.toString(), source);
	const all = state.update({ selection: EditorSelection.range(0, state.doc.length) }).state;
	assert.equal(all.sliceDoc(all.selection.main.from, all.selection.main.to), source);
	assert.equal(hidden(all).length, 0, 'selecting the source unfolds it without deleting it');
	const english = 'A circle at [composition] the top left (horizontal 0-1/3, vertical 0–1/3).';
	assert.equal(displayed(editor(english)), 'A circle at the top left.');
	for (const doc of [
		'左上（横2/3〜1、縦2/3〜1）に、円。',
		'左上（横0.1〜0.4、縦0.2〜0.5）に、円。',
		'画面の横0.2〜0.5、縦0〜0.3の範囲に、円。'
	]) assert.equal(displayed(editor(doc)), doc);
	assert.equal(displayed(editor(source, false, [])), source, 'no invented core range table');
});

test('entering opens ordinary text; name follows on leaving, with source and undo preserved', () => {
	let state = open(editor());
	assert.equal(hidden(state).length, 0);
	state = changeBody(state, '横０-１／３、縦０－１／３');
	assert.match(state.doc.toString(), /右下（横０-１／３/);
	assert.deepEqual(state.field(rangeEditorState).preview?.bounds, [0, 0, 1 / 3, 1 / 3]);
	state = state.update({ selection: { anchor: state.doc.length } }).state;
	assert.equal(state.doc.toString(), '  紙。\r\n［構図］左上（横０-１／３、縦０－１／３）に、赤い円。\n青い線。  ');
	assert.equal(displayed(state), '  紙。\r\n左上に、赤い円。\n青い線。  ');
	assert.equal(undo({ state, dispatch: (tr) => state = tr.state }), true);
	assert.match(state.doc.toString(), /右下（横０-１／３/, 'undo restores the old name without immediately renaming it');
	assert.equal(undo({ state, dispatch: (tr) => state = tr.state }), true);
	assert.equal(state.doc.toString(), source, 'undo does not immediately rename the restored source');
	state = changeBody(open(state), '横0.1〜0.4、縦0.2〜0.5');
	state = state.update({ effects: rangeFocusChanged.of(false) }).state;
	assert.match(state.doc.toString(), /右下（横0.1/);
	assert.equal(hidden(state).length, 0, 'custom bounds remain visible after blur');
	const en = changeBody(open(editor('A circle at the bottom right (horizontal 2/3 to 1, vertical 2/3 to 1).')), 'horizontal 0 to 1/3, vertical 0 to 1/3');
	assert.match(en.doc.toString(), /bottom right/);
	assert.match(en.update({ effects: rangeFocusChanged.of(false) }).newDoc.toString(), /top left/);
});

test('invalid and temporarily incomplete numbers keep the last valid frame until the edit is left', () => {
	let state = changeBody(open(editor()), '横0〜1/3、縦0〜1/3');
	const frame = state.field(rangeEditorState).preview!.bounds;
	for (const body of ['横1〜0、縦0〜1', 'typing']) {
		state = changeBody(state, body);
		assert.equal(state.field(rangeEditorState).invalid, true);
		assert.deepEqual(state.field(rangeEditorState).preview, { bounds: frame, invalid: true });
		assert.match(state.doc.toString(), new RegExp(body));
	}
	state = state.update({ selection: { anchor: state.doc.length } }).state;
	assert.equal(state.field(rangeEditorState).preview, null);
});

test('composition transactions defer folding and name changes through preedit and follow on leaving', () => {
	let state = open(editor());
	state = state.update({ effects: compositionChanged.of(true) }).state;
	const frame = state.field(rangeEditorState).preview;
	state = changeBody(state, '横0〜1/3、縦0〜1/3');
	state = state.update({ selection: { anchor: state.doc.length } }).state;
	assert.match(state.doc.toString(), /右下/);
	assert.equal(hidden(state).length, 0);
	assert.deepEqual(state.field(rangeEditorState).preview, frame);
	assert.equal(insertDdlWord(state, '青'), null, 'word insertion must not interrupt IME');
	state = state.update({ effects: compositionChanged.of(false) }).state;
	assert.match(state.doc.toString(), /左上/);
	assert.equal(state.field(rangeEditorState).composing, false);
	assert.ok(hidden(state).length > 0);
});

test('word insertion, read-only changes and external value synchronization use the actual document', () => {
	let state = editor('赤い円。');
	state = state.update({ selection: EditorSelection.range(0, 2) }).state;
	state = insertDdlWord(state, '青い')!.state;
	assert.equal(state.doc.toString(), '青い円。');
	assert.equal(state.selection.main.head, 2);
	const readonly = editor('保存した本文。', true);
	assert.equal(insertDdlWord(readonly, '削除'), null);
	assert.equal(readonly.update({ changes: { from: 0, to: readonly.doc.length, insert: '' } }).docChanged, false);
	const incoming = '別の本文。\r\n右下（横2/3〜1、縦2/3〜1）に、円。';
	const changed = replaceDdlValue(readonly, incoming)!.state;
	assert.equal(changed.doc.toString(), incoming);
	assert.equal(changed.readOnly, true);
	assert.equal(replaceDdlValue(changed, incoming), null, 'bind:value echo must not replace the document');
});

test('the editor decorations share the existing palette and qualified/unknown Macro semantics', () => {
	const doc = 'Nature.下草と、Nature.草、赤い円。';
	const state = editor(doc);
	const syntax = state.field(ddlSyntax);
	assert.equal(syntax.tokens.map((token) => token.part.text).join(''), doc);
	const marks: string[] = [];
	syntax.decorations.between(0, state.doc.length, (_from, _to, decoration) => marks.push(decoration.spec.class));
	for (const token of syntax.tokens) {
		const cls = ddlPartClass(token.part);
		if (cls) { assert.ok(marks.includes(cls)); assert.ok(highlightDDL(doc, null, names).includes(cls)); }
	}
	assert.deepEqual(unknownPluginNames(doc, names), [{ text: 'Nature.草', namespace: 'Nature', firesAs: 'Grass' }]);
	assert.ok(marks.includes('ddl-token ddl-token-unknown'));
});

test('cursor completions use the DDL language and canonical Macro names, and yield to numeric edits', async () => {
	let previews = 0;
	const source = ddlCompletions(() => ({ isJapanese: true,
		pluginEntries: [{ qualified_name: 'Nature.Grass', aliases: ['Nature.下草'], note_ja: '', note_en: '' }],
		previewForWord: () => { previews++; throw new Error('previews must be lazy'); },
		previewForPlugin: () => { previews++; throw new Error('previews must be lazy'); }, onPreview() {} }));
	const en = editor('Draw a red circle at the top left.\n');
	const completions = await source(new CompletionContext(en, en.doc.length, true));
	assert.ok(completions?.options.some((word) => word.label === 'Nature.Grass'));
	assert.ok(!completions?.options.some((word) => word.label === 'Nature.下草'));
	const ja = editor('赤い円。\n');
	const japanese = await source(new CompletionContext(ja, ja.doc.length, true));
	assert.ok(japanese?.options.some((word) => word.label === 'Nature.下草'));
	const numeric = open(editor());
	assert.equal(await source(new CompletionContext(numeric, numeric.selection.main.head, true)), null);
	assert.equal(await source(new CompletionContext(editor('', true), 0, true)), null);
	assert.equal(previews, 0);
});
