import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import ts from 'typescript';
import { EditorSelection, EditorState } from '@codemirror/state';
import { ddlEditorModel, insertDdlWord, replaceDdlValue } from './codemirror.ts';
import * as ddlControls from './codemirror.ts';
import { history, undo } from '@codemirror/commands';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
function actualFunction(path: string, name: string): string {
	const source = read(path);
	const start = source.indexOf('<script lang="ts">') + 18;
	const ast = ts.createSourceFile(path, source.slice(start, source.indexOf('</script>', start)), ts.ScriptTarget.Latest, true);
	const fn = ast.statements.find((node) => ts.isFunctionDeclaration(node) && node.name?.text === name);
	assert.ok(fn, `${path} has no ${name}`);
	return fn.getText(ast);
}
async function harness(source: string) {
	const code = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ESNext, module: ts.ModuleKind.ESNext } }).outputText;
	return import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'));
}
function actualMethod(path: string, name: string): string {
	const ast = ts.createSourceFile(path, read(path), ts.ScriptTarget.Latest, true);
	let method: ts.MethodDeclaration | undefined;
	function visit(node: ts.Node) {
		if (ts.isMethodDeclaration(node) && node.name.getText(ast) === name) method = node;
		ts.forEachChild(node, visit);
	}
	visit(ast);
	assert.ok(method, `${path} has no ${name}`);
	return method.getText(ast);
}

test('box and modal settings choose line numbers and commit complete drafts', async () => {
	const { setup } = await harness(`export function setup(compact, value, onChange, onRanges) {
		const isJapanese = true, disabled = false, pluginEntries = [], pluginNameIndex = {}, ranges = [];
		const previewForWord = () => {}, previewForPlugin = () => {};
		let activeSaijikiPreview = null;
		const t = () => ({ ddlEditorInstructions: 'instructions', ddlEditPlaceholder: 'placeholder' });
		${actualFunction('../../components/DdlEditor.svelte', 'configuration')}
		return { options: configuration(), value: () => value };
	}`);
	const source = '  紙。\r\n右下（横2/3〜1、縦2/3〜1）に、赤い円。  ';
	for (const compact of [true, false]) {
		const changed: string[] = [];
		const statuses: unknown[] = [];
		const editor = setup(compact, source, (next: string) => changed.push(next), (status: unknown) => statuses.push(status));
		assert.equal(editor.options.lineNumbers, !compact);
		assert.equal(editor.options.cursorAtEnd, compact);
		const next = source + '\r\n青い線。';
		editor.options.onChange(next);
		assert.equal(editor.value(), next);
		assert.deepEqual(changed, [next]);
		const status = { preview: { bounds: [0, 0, 0.5, 1], invalid: true }, invalid: true, composing: true };
		editor.options.onRanges(status);
		assert.deepEqual(statuses, [status]);
	}
	const model = read('./codemirror.ts');
	assert.match(model, /options\.lineNumbers === false \? \[\] : lineNumbers\(\)/, 'the live extension honors the choice');
	assert.match(model, /selection: initial\.cursorAtEnd \? EditorSelection\.cursor\(value\.length\) : undefined/, 'an untouched box starts at the end');
	const viewer = read('../../components/DdlViewer.svelte');
	assert.match(viewer, /value=\{ddl\}/, 'the shared editor gets complete source, not rendered HTML');
	assert.match(viewer, /compact/);
	assert.match(viewer, /editDisabled \|\| !onDdlChange/);
	assert.match(viewer, /rangeStatus\.composing/);
	const page = read('../../../routes/+page.svelte');
	const start = page.indexOf('onDdlChange=');
	const edit = page.slice(start, page.indexOf('onRangePreview=', start));
	assert.match(edit, /canEditCurrentDdl && !rangeEditingLocked/);
	assert.match(edit, /work\.ddl = ddl/);
	assert.doesNotMatch(edit, /replay|authorDdl|apiFetch/, 'typing only commits a draft');
	assert.match(read('../../i18n/ja.ts'), /ddlEditButton: '指示書エディタ'/);
	assert.match(read('../../i18n/en.ts'), /workActionInstructions: 'Instruction editor'/);
});

test('the drawer inserts at the box caret, appends before focus, and only previews when editing is unavailable', async () => {
	const { setup } = await harness(`export function setup(ddlViewer, canEditCurrentDdl, rangeEditingLocked, ddlDialogOpen) {
		${actualFunction('../../../routes/+page.svelte', 'insertDdlWordFromDrawer')}
		return insertDdlWordFromDrawer;
	}`);
	const { drawer } = await harness(`export function drawer(onInsertWord) {
		let activePreview = null;
		${actualFunction('../../components/SaijikiDrawer.svelte', 'selectWord')}
		return { selectWord, preview: () => activePreview };
	}`);
	const raw = '  赤い円。\r\n青い線。  ';
	const model = ddlEditorModel([], { names: [], firesOn: [] });
	const { control } = await harness(`export function control(view, options, cursorPlaced, insertDdlWord) {
		return { ${actualMethod('./codemirror.ts', 'insertWord')} };
	}`);
	function box(selection: ReturnType<typeof EditorSelection.cursor>, readOnly = false, cursorPlaced = true) {
		let state = EditorState.create({ doc: raw, selection, extensions: readOnly ? ddlEditorModel([], { names: [], firesOn: [] }, true) : model });
		const view = { get state() { return state; }, dispatch(tr: { state: EditorState }) { state = tr.state; }, focus() {} };
		return { ...control(view, { cursorAtEnd: true }, cursorPlaced, insertDdlWord), value: () => state.doc.toString(),
			setValue(next: string) { const tr = replaceDdlValue(state, next); if (tr) state = tr.state; } };
	}
	const preview = { word: 'Nature.風', image: '/api/saijiki/preview' };
	for (const position of [raw.indexOf('青い線'), raw.length]) {
		const editor = box(EditorSelection.cursor(position));
		const reference = drawer(setup(editor, true, false, false));
		reference.selectWord('Nature.風', preview);
		assert.equal(editor.value(), raw.slice(0, position) + 'Nature.風' + raw.slice(position));
		assert.equal(reference.preview(), preview);
	}
	const untouched = box(EditorSelection.cursor(raw.length), false, false);
	const updated = raw + '\r\n別の文。';
	untouched.setValue(updated);
	drawer(setup(untouched, true, false, false)).selectWord('円', preview);
	assert.equal(untouched.value(), updated + '円', 'before the first caret, an external update still appends at the current end');
	const selected = box(EditorSelection.range(raw.indexOf('青い線'), raw.indexOf('青い線') + 3));
	drawer(setup(selected, true, false, false)).selectWord('赤い円', preview);
	assert.equal(selected.value(), raw.replace('青い線', '赤い円'));
	for (const [canEdit, locked, modal, present, readOnly] of [
		[false, false, false, true, false], [true, true, false, true, false],
		[true, false, true, true, false], [true, false, false, false, false],
		[true, false, false, true, true]
	]) {
		const editor = box(EditorSelection.cursor(raw.length), readOnly);
		const reference = drawer(setup(present ? editor : null, canEdit, locked, modal));
		reference.selectWord('Nature.風', preview);
		assert.equal(editor.value(), raw);
		assert.equal(reference.preview(), preview);
	}
	const standalone = drawer(undefined);
	standalone.selectWord('円', preview);
	assert.equal(standalone.preview(), preview);
	const component = read('../../components/SaijikiDrawer.svelte');
	assert.match(component, /selectWord\(word, previewForWord\(/, 'a built-in click inserts its displayed word');
	assert.match(component, /selectWord\(pluginDisplayName\(entry, wordLang\), previewForPlugin\(/, 'a Macro click inserts its displayed name');
	assert.equal((component.match(/onpointerdown=\{\(e\) => e\.preventDefault\(\)\}/g) ?? []).length, 2, 'clicking keeps the box selection');
});

test('discard edits in the box confirms before changing the draft and guards the target', async () => {
	const { setup } = await harness(`export function setup(props, onConfirmDiscard) {
		let { ddl, savedDdl, readOnly = false, paintDisabled = false, rangeStatus = { composing: false }, workKey, editor } = props;
		${actualFunction('../../components/DdlViewer.svelte', 'canDiscardEdits')}
		${actualFunction('../../components/DdlViewer.svelte', 'requestDiscardEdits')}
		return { canDiscardEdits, requestDiscardEdits, set(patch) {
			({ ddl = ddl, savedDdl = savedDdl, readOnly = readOnly, paintDisabled = paintDisabled, rangeStatus = rangeStatus, workKey = workKey, editor = editor } = patch);
		} };
	}`);
	const { control } = await harness(`export function control(view, replaceDdlWithHistory) {
		return { ${actualMethod('./codemirror.ts', 'replaceValueWithHistory')} };
	}`);
	const saved = '保存した円。\r\n青い線。';
	const draft = saved + '\r\n下書き。';
	let state = EditorState.create({ doc: draft, extensions: [ddlEditorModel([], { names: [], firesOn: [] }), history()] });
	let workDdl = draft, focuses = 0;
	let confirmation: { run: () => void; cancel: () => void } | null = null;
	const view = { get state() { return state; }, composing: false, dispatch(tr: { state: EditorState }) { state = tr.state; workDdl = state.doc.toString(); box.set({ ddl: workDdl }); }, focus() { focuses++; } };
	const editor = { ...control(view, Reflect.get(ddlControls, 'replaceDdlWithHistory')), focus() { focuses++; } };
	const box = setup({ ddl: draft, savedDdl: saved, editor, workKey: 'work-1' }, (run: () => void, cancel: () => void) => confirmation = { run, cancel });
	assert.equal(box.canDiscardEdits(), true);
	box.requestDiscardEdits();
	assert.equal(workDdl, draft, 'asking does not discard or draw');
	assert.ok(confirmation);
	(confirmation as { cancel: () => void }).cancel();
	assert.equal(workDdl, draft);
	assert.equal(focuses, 1);
	box.requestDiscardEdits();
	(confirmation as { run: () => void }).run();
	assert.equal(workDdl, saved);
	assert.equal(box.canDiscardEdits(), false);
	assert.equal(undo({ state, dispatch: (tr) => view.dispatch(tr) }), true);
	assert.equal(workDdl, draft);
	for (const patch of [{ readOnly: true }, { paintDisabled: true }, { rangeStatus: { composing: true } }, { savedDdl: null }, { ddl: saved }]) {
		box.set({ ddl: draft, savedDdl: saved, readOnly: false, paintDisabled: false, rangeStatus: { composing: false }, ...patch });
		confirmation = null;
		assert.equal(box.canDiscardEdits(), false);
		box.requestDiscardEdits();
		assert.equal(confirmation, null);
	}
	box.set({ ddl: draft, savedDdl: saved });
	box.requestDiscardEdits();
	assert.ok(confirmation);
	box.set({ workKey: 'work-2' });
	(confirmation as { run: () => void }).run();
	assert.equal(workDdl, draft, 'a confirmation for a different work cannot discard this draft');
	box.set({ workKey: 'work-1' });
	box.requestDiscardEdits();
	box.set({ paintDisabled: true });
	(confirmation as { run: () => void }).run();
	assert.equal(workDdl, draft, 'drawing that started during confirmation blocks the discard');
	const { ask } = await harness(`export function ask(t, confirmationDialog, tick) {
		let confirmAction = null;
		${actualFunction('../../../routes/+page.svelte', 'confirmDiscardEdits')}
		return { run: confirmDiscardEdits, action: () => confirmAction };
	}`);
	const action = ask(() => ({ ddlDiscardMessage: 'saved work', ddlDiscardConfirm: 'Discard' }));
	action.run(() => {}, () => {});
	assert.equal(action.action().message, 'saved work');
	assert.equal(action.action().runLabel, 'Discard');
	assert.equal(action.action().destructive, true);
	assert.equal(action.action().focusOnOpen, true);
	const { keys } = await harness(`export function keys(dialog, document, onCancel) {
		const focusOnOpen = true;
		${actualFunction('../../components/ConfirmDialog.svelte', 'handleKeydown')}
		return handleKeydown;
	}`);
	let active = '', cancelled = false, prevented = false, stopped = false;
	const cancel = { focus() { active = 'cancel'; } }, discard = { focus() { active = 'discard'; } };
	const keydown = keys({ querySelectorAll: () => [cancel, discard] }, { activeElement: discard }, () => cancelled = true);
	keydown({ key: 'Tab', preventDefault() { prevented = true; } });
	assert.equal(active, 'cancel');
	assert.equal(prevented, true);
	keydown({ key: 'Escape', preventDefault() {}, stopPropagation() { stopped = true; } });
	assert.equal(cancelled, true);
	assert.equal(stopped, true, 'Escape cancels the confirmation before reaching the editor');
	const page = read('../../../routes/+page.svelte');
	assert.match(page, /savedDdl=\{work\.ddlGeneratedBaseline\}/);
	assert.match(read('../../components/DdlViewer.svelte'), /disabled=\{!canDiscardEdits\(\)\}/);
});

test('discard edits in the dialog uses the saved target, leaves the box alone, and is absent in new mode', async () => {
	const { setup } = await harness(`export function setup(props, onConfirmDiscard) {
		let { open = true, mode = 'edit', value, savedDdl, drawing = false, discardDisabled = false, rangeStatus = { composing: false }, editor } = props;
		${actualFunction('../../components/DdlEditorDialog.svelte', 'canDiscardEdits')}
		${actualFunction('../../components/DdlEditorDialog.svelte', 'requestDiscardEdits')}
		return { canDiscardEdits, requestDiscardEdits, set(patch) {
			({ mode = mode, value = value, savedDdl = savedDdl, drawing = drawing, discardDisabled = discardDisabled, rangeStatus = rangeStatus, editor = editor } = patch);
		} };
	}`);
	const boxDraft = '箱の下書き。', saved = '対象作品の保存した本文。';
	let dialogValue = boxDraft, confirmation: { run: () => void; cancel: () => void } | null = null;
	const editor = { replaceValueWithHistory(next: string) { dialogValue = next; dialog.set({ value: next }); }, focus() {} };
	const dialog = setup({ value: boxDraft, savedDdl: saved, editor }, (run: () => void, cancel: () => void) => confirmation = { run, cancel });
	dialog.requestDiscardEdits();
	assert.ok(confirmation);
	assert.equal(dialogValue, boxDraft);
	(confirmation as { cancel: () => void }).cancel();
	assert.equal(dialogValue, boxDraft);
	dialog.requestDiscardEdits();
	(confirmation as { run: () => void }).run();
	assert.equal(dialogValue, saved, 'return to the saved target rather than the opening draft');
	assert.equal(boxDraft, '箱の下書き。');
	assert.equal(dialog.canDiscardEdits(), false);
	for (const patch of [{ mode: 'new' }, { drawing: true }, { discardDisabled: true }, { rangeStatus: { composing: true } }, { value: saved }, { savedDdl: null }]) {
		dialog.set({ mode: 'edit', value: boxDraft, savedDdl: saved, drawing: false, discardDisabled: false, rangeStatus: { composing: false }, ...patch });
		confirmation = null;
		assert.equal(dialog.canDiscardEdits(), false);
		dialog.requestDiscardEdits();
		assert.equal(confirmation, null);
	}
	const component = read('../../components/DdlEditorDialog.svelte');
	assert.match(component, /\{#if mode === 'edit' && savedDdl !== null && onConfirmDiscard\}/);
	assert.match(component, /disabled=\{!canDiscardEdits\(\)\}/);
	assert.match(read('../../../routes/+page.svelte'), /savedDdl=\{ddlDialogNode\?\.history\?\.ddl \?\? null\}/);
});
