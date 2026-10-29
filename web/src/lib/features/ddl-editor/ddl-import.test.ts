import assert from 'node:assert/strict';
import test from 'node:test';

import { parseDdlImport } from './ddl-import.ts';

const definition = { schema: 'inku.macro-definition.v2', namespace: 'Nature', id: 'YoungLeaves', names: { ja: ['若葉'], en: ['young leaves'] }, kind: 'scene', version: '1.0.1', parameters: {}, components: {}, body: [] };

test('an export restores its DDL and carries the saved plugin definitions', () => {
	const read = parseDdlImport(JSON.stringify({
		schema: 'inku.ddl-export.v2', language: 'ja', ddl: '背景を白で埋める。\n｛若葉｝。',
		plugins: [{ definition, note: '若葉を上半分へ散らす。' }], exported_from: {},
	}));
	assert.equal(read.ddl, '背景を白で埋める。\n｛若葉｝。');
	assert.deepEqual(read.plugins, [{ definition, note: '若葉を上半分へ散らす。' }]);
	assert.deepEqual(read.names, ['Nature.YoungLeaves']);
});

test('plain text and unrelated JSON stay the author\'s text without definitions', () => {
	assert.deepEqual(parseDdlImport('中央に赤い円を置く。'), { ddl: '中央に赤い円を置く。', plugins: [], names: [] });
	assert.equal(parseDdlImport('{"a":1}').ddl, '{"a":1}');
});

test('a malformed export is refused instead of silently dropping its plugins', () => {
	assert.throws(() => parseDdlImport(JSON.stringify({ schema: 'inku.ddl-export.v1', ddl: 'x' })), /ddl_export_requires_v2/);
	assert.throws(() => parseDdlImport(JSON.stringify({ schema: 'inku.ddl-export.v2', plugins: [] })), /ddl_export_without_ddl/);
	assert.throws(() => parseDdlImport(JSON.stringify({ schema: 'inku.ddl-export.v2', ddl: 'x', plugins: [{ note: 's' }] })), /ddl_export_invalid_plugin/);
});
