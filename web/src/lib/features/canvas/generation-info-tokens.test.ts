import assert from 'node:assert/strict';
import { test } from 'node:test';

import { en } from '../../i18n/en.ts';
import { ja } from '../../i18n/ja.ts';
import {
	tokenDetailFromSettings,
	tokenStageLabel,
	tokenStageRows,
	TOKEN_DETAIL_FIELD,
	TOKEN_STAGES,
	type ProviderStageUsage
} from './generation-info-tokens';

const usage = (sends: number, input: number | null = 10, output: number | null = 2): ProviderStageUsage => ({
	sends,
	unreported_sends: 0,
	input_tokens: input,
	output_tokens: output,
	cached_input_tokens: null
});

test('the total alone shows for an account that never chose', () => {
	assert.equal(tokenDetailFromSettings(null), false);
	assert.equal(tokenDetailFromSettings({}), false);
	assert.equal(tokenDetailFromSettings({ [TOKEN_DETAIL_FIELD]: 'yes' }), false);
	assert.equal(tokenDetailFromSettings({ [TOKEN_DETAIL_FIELD]: true }), true);
});

test('the stages that sent are rowed in the order a work calls them', () => {
	const rows = tokenStageRows({ stage2: usage(1), laws: usage(1), stage1: usage(2), later: usage(1), colors: usage(0) });
	assert.deepEqual(rows.map((row) => row.stage), ['stage1', 'laws', 'stage2', 'later']);
	assert.deepEqual(tokenStageRows(null), []);
});

test('every stage the server times is named in both languages, and a later one by its own name', () => {
	for (const messages of [ja, en]) {
		for (const stage of TOKEN_STAGES) assert.ok(tokenStageLabel(stage, messages));
		assert.equal(tokenStageLabel('later', messages), 'later');
	}
	assert.equal(tokenStageLabel('laws', ja), '法則');
});
