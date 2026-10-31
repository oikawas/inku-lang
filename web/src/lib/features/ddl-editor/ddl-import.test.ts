import assert from 'node:assert/strict';
import test from 'node:test';

import { importDdl, parseDdlImport } from './ddl-import.ts';

const definition = { schema: 'inku.macro-definition.v2', namespace: 'Nature', id: 'YoungLeaves', names: { ja: ['若葉'], en: ['young leaves'] }, kind: 'scene', version: '1.0.1', parameters: {}, components: {}, body: [] };

test('an export restores its DDL and carries the saved plugin definitions', () => {
	const read = parseDdlImport(JSON.stringify({
		schema: 'inku.ddl-export.v2', language: 'ja', ddl: '背景を白で埋める。\n｛若葉｝。',
		plugins: [{ definition, note: '若葉を上半分へ散らす。' }], exported_from: {},
	}));
	assert.equal(read.ddl, '背景を白で埋める。\n｛若葉｝。');
	assert.deepEqual(read.plugins, [{ definition, note: '若葉を上半分へ散らす。' }]);
	assert.deepEqual(read.names, ['｛若葉｝']);
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

test('an older export is migrated before the DDL is accepted', async () => {
	const text = JSON.stringify({ schema: 'inku.ddl-export.v2', language: 'ja', ddl: '黒い太筆の線を引く。', plugins: [] });
	let called = false;
	const result = await importDdl(text, 'ja', async (path, init) => {
		called = true;
		assert.equal(path, '/api/ddl-export/migrate-v2');
		assert.equal(JSON.parse(String(init?.body)).ddl, '黒い太筆の線を引く。');
		return Response.json({ ddl: '黒い太いガッシュの線を引く。', plugins: [], edits: 1 });
	});
	assert.equal(called, true);
	assert.equal(result.ddl, '黒い太いガッシュの線を引く。');
	assert.equal(result.edits, 1);
	await assert.rejects(importDdl(text, 'ja', async () => new Response('', { status: 422 })));
});
