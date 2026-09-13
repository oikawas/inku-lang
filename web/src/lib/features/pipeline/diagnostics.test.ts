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
