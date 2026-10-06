import assert from 'node:assert/strict';
import test from 'node:test';
import { readFileSync } from 'node:fs';
import { ja } from '../../i18n/ja.ts';
import { en } from '../../i18n/en.ts';

test('completion reasons use the specified plain words in both languages and keep unknown codes', () => {
	assert.equal(typeof ja.pipelineCompletionReason, 'function');
	const reasons = [
		['established_fact_changed', '元の文で読めた語（位置・個数・色・形・動作など）が案で消えた', 'The proposal lost a word read in the original sentence (a place, count, colour, shape, action, …).'],
		['owner_association_changed', '語と形の結びつきが案で変わった', 'The proposal changed which shape a word belongs to.'],
		['target_unresolved', '案にも読めない語が残り、描ける文にならなかった', 'The proposal still had words that could not be read, so it could not be drawn.'],
		['new_diagnostic', '案に新しい読めない語句が入った', 'The proposal added a phrase that could not be read.'],
		['numeric_range_outside_words', '数の範囲が、括弧の前の位置の語の範囲から外れた', 'The numeric range fell outside the place word before the parenthesis.'],
		['dependency_rejected', '一緒に直す別の文が補えなかった', 'Another sentence that has to be fixed with it could not be completed.'],
		['dependency_unresolved', '一緒に直す別の文が補えなかった', 'Another sentence that has to be fixed with it could not be completed.'],
		['outside_explicit_changed', '案が穴の外の書いた内容を変えた', 'The proposal changed what is written outside the gap.'],
		['schema_violation', 'モデルの答えが読めなかった', "The model's answer could not be read."],
		['unsupported', '今の文法では書けないと答えた', 'The model answered that the current grammar cannot write it.'],
		['ambiguous', '意味を一つに決められないと答えた', 'The model answered that the meaning cannot be decided.'],
		['context_limit', '文脈が長すぎて補えなかった', 'The context was too long to complete.'],
	];
	for (const [code, japanese, english] of reasons) {
		assert.equal(ja.pipelineCompletionReason(code), japanese);
		assert.equal(en.pipelineCompletionReason(code), english);
	}
	assert.equal(ja.pipelineCompletionReason('future_reason'), '検査で断られた（future_reason）');
	assert.equal(en.pipelineCompletionReason('future_reason'), 'Refused by the check (future_reason).');
	assert.doesNotMatch(ja.pipelineAttentionReason('hole_completion_context_limit'), /hole_completion_context_limit/);
	assert.doesNotMatch(en.pipelineAttentionReason('hole_completion_context_limit'), /hole_completion_context_limit/);
});

test('completion issues show only uncompleted holes at a stop or approval and retain author source', async () => {
	const { holeCompletionIssues } = await import('./hole-completion.ts');
	const source = '<b>右寄り</b>に、青い円。\r\n線。';
	const check = { results: [
		{ hole_id: 'first', status: 'rejected' as const, reason: 'numeric_range_outside_words', source, proposal: 'model proposal' },
		{ hole_id: 'second', status: 'unresolved' as const, reason: 'unsupported', source: '前の形の周り。' },
		{ hole_id: 'third', status: 'validated' as const, reason: null, source: '通った文。' },
	] };
	const stopped = { phase: { tag: 'needs_user_edit', reason: 'hole_completion_failed' }, hole_completion_check: check };
	const expected = [
		{ holeId: 'first', source, reason: '数の範囲が、括弧の前の位置の語の範囲から外れた' },
		{ holeId: 'second', source: '前の形の周り。', reason: '今の文法では書けないと答えた' },
	];
	assert.deepEqual(holeCompletionIssues(stopped, ja), expected);
	assert.deepEqual(holeCompletionIssues({ ...stopped, phase: { tag: 'needs_user_edit', reason: 'hole_completion_context_limit' } }, ja), expected);
	assert.deepEqual(holeCompletionIssues({ ...stopped, phase: { tag: 'awaiting_patch_approval' } }, ja), expected);
	assert.deepEqual(holeCompletionIssues({ ...stopped, phase: { tag: 'awaiting_llm' } }, ja), []);
	assert.deepEqual(holeCompletionIssues({ ...stopped, phase: { tag: 'needs_user_edit', reason: 'stage1_failed' } }, ja), []);
	assert.deepEqual(holeCompletionIssues(null, ja), []);
	const legacy = { ...stopped, hole_completion_check: { results: [{ hole_id: 'old', status: 'rejected' as const, reason: 'future_reason', proposal: 'never substitute model text' }] } };
	assert.deepEqual(holeCompletionIssues(legacy, en), [{ holeId: 'old', source: '', reason: 'Refused by the check (future_reason).' }]);
	const component = readFileSync(new URL('../../components/PipelineStatus.svelte', import.meta.url), 'utf8');
	assert.match(component, /\{#each completionIssues as issue/);
	assert.match(component, /<pre>\{issue\.source\}<\/pre>/);
	assert.match(component, /\{issue\.reason\}/);
	assert.doesNotMatch(component, /\{@html/);
	const page = readFileSync(new URL('../../../routes/+page.svelte', import.meta.url), 'utf8');
	assert.match(page, /completionIssues=\{holeCompletionIssues\(work\.pipelineView, t\(\)\)\}/);
});
