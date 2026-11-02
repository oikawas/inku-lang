import assert from 'node:assert/strict';
import { test } from 'node:test';
import { ja } from '../../i18n/ja.ts';
import { en } from '../../i18n/en.ts';
import { batchElapsedTime } from './elapsed.ts';

test('batch time and row labels follow the Japanese and English boundaries', () => {
	assert.deepEqual([45, 60, 723, 3723].map((s) => batchElapsedTime(s * 1000, ja)),
		['45 秒', '1 分 00 秒', '12 分 03 秒', '1 時間 02 分 03 秒']);
	assert.deepEqual([45, 60, 723, 3723].map((s) => batchElapsedTime(s * 1000, en)),
		['45 s', '1 min 00 s', '12 min 03 s', '1 h 02 min 03 s']);
	assert.equal(ja.batchRowOfTotal(3, 8), '8 行中 3 行目');
	assert.equal(en.batchRowOfTotal(3, 8), 'line 3 of 8');
	assert.equal(ja.batchElapsed('45 秒'), 'バッチ開始から 45 秒');
	assert.equal(en.batchElapsed('45 s'), '45 s since the batch started');
});
