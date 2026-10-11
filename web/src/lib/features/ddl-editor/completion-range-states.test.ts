import assert from 'node:assert/strict';
import test from 'node:test';
import { EditorState } from '@codemirror/state';
import { en } from '../../i18n/en.ts';
import { ja } from '../../i18n/ja.ts';
import { readCompositionRanges } from '../../composition-ranges.ts';
import { ddlEditorModel } from './codemirror.ts';
import { openRangeAt, rangeEditorState } from './codemirror-ranges.ts';
import { completionRangeTagState, completionRangeTagsChanged } from './completion-range-tags.ts';
import { CompletionRangeStatesQuery, completionWordsHint, type CompletionRangeState } from './completion-range-states.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';

const table = readCompositionRanges({ schema: 'inku.composition-ranges.v1', ranges: [
	{ key: 'left', words: { ja: '左上', en: 'top left' }, bounds: [[0, 1], [0, 1], [1, 3], [1, 3]], corner: false },
	{ key: 'right', words: { ja: '右下', en: 'bottom right' }, bounds: [[2, 3], [2, 3], [1, 1], [1, 1]], corner: false }
] });
const range = '右下（横2/3〜1、縦2/3〜1）';
const source = `  🌙\r\n${range}に、円。\n${range}に、線。\n${range}に、点。  `;
const states = ['completed', 'numbers_changed', 'words_changed'].map((state, i) => {
	const start = i === 0 ? source.indexOf(range) : source.indexOf(range, source.indexOf(range) + range.length + (i === 2 ? range.length + 5 : 0));
	return { utf16_start: start, utf16_end: start + range.length, state } as CompletionRangeState;
});
const labels = (strings: typeof ja) => ({ completed: strings.ddlCompletionTag, numbers_changed: strings.ddlCompletionNumbersTag, words_changed: strings.ddlCompletionWordsTag });
function editor(doc = source) {
	return EditorState.create({ doc, selection: { anchor: doc.length }, extensions: [
		ddlEditorModel(table, { names: [], firesOn: [] }), completionRangeTagState
	] });
}
function widgets(state: EditorState) {
	const result: { at: number; label: string; state: string }[] = [];
	state.field(completionRangeTagState).decorations.between(0, state.doc.length, (from, _to, decoration) => {
		result.push({ at: from, label: decoration.spec.widget.label, state: decoration.spec.widget.state });
	});
	return result;
}

test('A3 tags use core UTF-16 ends, keep raw source and folding, and do not reset numeric name following', () => {
	for (const strings of [ja, en]) {
		const original = editor();
		const shown = original.update({ effects: completionRangeTagsChanged.of({ source, ranges: states, labels: labels(strings) }) }).state;
		assert.equal(shown.doc.toString(), source);
		assert.deepEqual(widgets(shown), states.map((row) => ({ at: row.utf16_end, label: labels(strings)[row.state], state: row.state })));
		assert.equal(shown.field(rangeEditorState).atomic.size, original.field(rangeEditorState).atomic.size);
		assert.equal(shown.field(rangeEditorState).decorations.size, original.field(rangeEditorState).decorations.size);
		const next = shown.update({ changes: { from: 0, insert: '新' } }).state;
		assert.deepEqual(widgets(next), [], 'old positions disappear as soon as the draft changes');
		assert.deepEqual(widgets(next.update({ effects: completionRangeTagsChanged.of({ source, ranges: states, labels: labels(strings) }) }).state), []);
	}
	let state = editor(range + 'に、円。');
	state = openRangeAt(state, 0)!.state;
	const active = state.field(rangeEditorState).active!;
	state = state.update({ changes: { from: active.bodyStart, to: active.bodyEnd, insert: '横0〜1/3、縦0〜1/3' }, userEvent: 'input' }).state;
	assert.equal(state.field(rangeEditorState).pendingName, true);
	state = state.update({ effects: completionRangeTagsChanged.of({ source: state.doc.toString(), ranges: [], labels: labels(ja) }) }).state;
	assert.equal(state.field(rangeEditorState).pendingName, true, 'an async record response must not reconfigure numeric editing');
	state = state.update({ selection: { anchor: state.doc.length } }).state;
	assert.match(state.doc.toString(), /^左上（横0〜1\/3/);
});

test('A3 lower line appears only for edited words and the refusal reason uses the specified ja/en text', () => {
	for (const strings of [ja, en]) {
		assert.equal(completionWordsHint(states.slice(0, 2), strings), null);
		assert.equal(completionWordsHint([], strings), null);
	}
	assert.equal(completionWordsHint(states, ja), '言葉を直した範囲が 1 つあります。描くと補完がその範囲の数を書き直し、承認を求めます。');
	assert.equal(completionWordsHint(states, en), 'One range has edited words. Drawing asks the completion to rewrite its numbers and asks for your approval.');
	assert.equal(completionWordsHint([states[2], states[2]], ja), '言葉を直した範囲が 2 つあります。描くと補完がその範囲の数を書き直し、承認を求めます。');
	assert.equal(completionWordsHint([states[2], states[2]], en), '2 ranges have edited words. Drawing asks the completion to rewrite their numbers and asks for your approval.');
	assert.equal(ja.pipelineCompletionReason('range_words_not_kept'), '言葉を直した範囲の、括弧の前の言葉か範囲の形が案で変わった');
	assert.equal(en.pipelineCompletionReason('range_words_not_kept'), 'The proposal changed the edited words before the parenthesis, or the form of the range.');
});

test('A3 requests retain the editor raw source and reject late responses from an earlier source or work', async () => {
	const requests: { body: unknown; signal: AbortSignal | null | undefined; resolve: (response: Response) => void }[] = [];
	const apiFetch: ApiFetch = async (_path, init) => new Promise<Response>((resolve) => requests.push({ body: JSON.parse(init!.body as string), signal: init?.signal, resolve }));
	const query = new CompletionRangeStatesQuery();
	const published: CompletionRangeState[][] = [];
	const first = query.load(apiFetch, { history_id: 'old-work' }, source, (value) => published.push(value));
	const nextSource = source + '\r\n青い線。  ';
	const second = query.load(apiFetch, { execution_id: 'current-run' }, nextSource, (value) => published.push(value));
	assert.equal(requests[0].signal?.aborted, true);
	assert.deepEqual(requests[1].body, { execution_id: 'current-run', source: nextSource });
	requests[1].resolve(Response.json({ schema: 'inku.completion-range-states.v1', ranges: [states[2]] }));
	await second;
	requests[0].resolve(Response.json({ schema: 'inku.completion-range-states.v1', ranges: states }));
	await first;
	assert.deepEqual(published, [[states[2]]]);
	const closing = query.load(apiFetch, { history_id: 'closed-editor' }, source, (value) => published.push(value));
	query.cancel();
	requests[2].resolve(Response.json({ schema: 'inku.completion-range-states.v1', ranges: states }));
	await closing;
	assert.deepEqual(published, [[states[2]]]);
});
