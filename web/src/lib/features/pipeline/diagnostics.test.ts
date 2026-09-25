import assert from 'node:assert/strict';
import test from 'node:test';

import { ja } from '../../i18n/ja.ts';
import { formatPipelineDiagnostic } from './diagnostics.ts';

test('resource omission names its owner, limit, omitted part, and continued drawing', () => {
	const actual = formatPipelineDiagnostic({
		channel: 'resource',
		value: {
			cause: {
				owner: { kind: 'object', value: { instruction_index: 0, kind: 'source_instruction' } },
				reason: {
					kind: 'budget_exceeded',
					value: { authority: 'hard_policy', dimension: 'logical_objects', maximum: 400, required: 6945 },
				},
			},
			owner: { kind: 'source_instruction', value: { source_instruction_index: 0 } },
		},
	}, ja);

	assert.equal(
		actual,
		'原文の指示 1 の箇所。 描画対象の数は 6945 必要でしたが、上限は 400 でした。 原文の指示 1 を省略しました。 ほかの部分の描画は続けました。',
	);
});

test('partial resource execution names requested and drawn counts without saying the instruction was omitted', () => {
	const actual = formatPipelineDiagnostic({
		channel: 'resource',
		value: {
			cause: {
				owner: { kind: 'object', value: { instruction_index: 0, kind: 'source_instruction' } },
				reason: {
					kind: 'budget_exceeded',
					value: { authority: 'hard_policy', dimension: 'maximum_per_template_primitive_marks', maximum: 240, required: 300 },
				},
			},
			owner: { kind: 'source_instruction', value: { source_instruction_index: 0 } },
			partial_execution: { requested_count: 300, executed_count: 240 },
		},
	}, ja);

	assert.equal(
		actual,
		'原文の指示 1 の箇所。 一つの描画指示が描く印の数は 300 必要でしたが、上限は 240 でした。 300個の要求のうち、実行可能な240個を描画しました。 ほかの部分の描画は続けました。',
	);
});

test('saved render clip omission names its instruction, reason, omission, and continuation', () => {
	const actual = formatPipelineDiagnostic({
		channel: 'render',
		value: {
			instruction_index: 2,
			reason: 'fill_clip_limit_exceeded',
			disposition: 'omitted',
		},
	}, ja);

	assert.equal(
		actual,
		'描画指示 3 の箇所。 クリップ処理の上限を超えました。 描画指示 3 を省略しました。 ほかの部分の描画は続けました。',
	);
});

test('a withheld plugin sentence is explained in the author\'s language', () => {
	assert.equal(
		formatPipelineDiagnostic({ channel: 'plugin', value: { name: 'Nature.若菜', reason: 'plugin_name_mismatch', suggestion: 'Nature.若葉', start_byte: 28, end_byte: 42 } }, ja),
		'プラグイン Nature.若菜 は登録名と一致しないため、この文は描かれていません。Nature.若葉 のことですか。',
	);
	assert.equal(
		formatPipelineDiagnostic({ channel: 'plugin', value: { name: 'Garden.薔薇', reason: 'plugin_not_installed', start_byte: 0, end_byte: 1 } }, ja),
		'プラグイン Garden.薔薇 はこの環境に登録されていないため、この文は描かれていません。',
	);
});
