import assert from 'node:assert/strict';
import test from 'node:test';
import { annotate } from './highlight.ts';
import { PluginCallsQuery, type PluginCall } from './features/ddl-editor/plugin-calls.ts';

test('the core ranges own the complete plugin word, including its inner colors', () => {
	const text = '｛青葉｝と｛不明｝。';
	const calls: PluginCall[] = [
		{ start_byte: 0, end_byte: 12, start_utf16: 0, end_utf16: 4, text: '｛青葉｝', spelling: 'braced', status: 'resolved', qualified_name: 'Nature.SummerLeaves' },
		{ start_byte: 15, end_byte: 27, start_utf16: 5, end_utf16: 9, text: '｛不明｝', spelling: 'braced', status: 'plugin_not_installed' },
	];
	const parts = annotate(text, calls, true);
	assert.deepEqual(parts.filter(part => part.kind === 'plugin-name').map(part => [part.text, part.known]), [['｛青葉｝', true], ['｛不明｝', false]]);
	assert.ok(!parts.some(part => part.kind === 'saijiki' && part.text === '青'));
});

test('a late answer is discarded when the draft changes', async () => {
	const query = new PluginCallsQuery();
	let finish!: (response: Response) => void;
	const pending = new Promise<Response>(resolve => { finish = resolve; });
	const seen: PluginCall[][] = [];
	const old = query.load(async () => pending, null, '｛古い｝。', 'ja', calls => seen.push(calls));
	await query.load(async () => new Response(JSON.stringify({ schema: 'inku.plugin-calls.v1', calls: [] })), null, '｛新しい｝。', 'ja', calls => seen.push(calls));
	finish(new Response(JSON.stringify({ schema: 'inku.plugin-calls.v1', calls: [{ text: 'old' }] })));
	await old;
	assert.deepEqual(seen, [[]]);
});
