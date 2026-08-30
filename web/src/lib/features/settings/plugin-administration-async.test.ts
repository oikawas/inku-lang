import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const source = readFileSync(new URL('./PluginAdministrationSettings.svelte', import.meta.url), 'utf8');

function region(startMarker: string, endMarker: string): string {
	const start = source.indexOf(startMarker);
	const end = source.indexOf(endMarker, start + startMarker.length);
	assert.ok(start >= 0 && end > start, `${startMarker} region`);
	return source.slice(start, end);
}

test('only the latest plugin content request may populate the editor', () => {
	assert.match(source, /let pluginEditorLoadRequestId = 0;/);
	const open = region('async function openPluginEditor', 'function closePluginEditor');
	const awaited = open.indexOf('await onLoadPluginContent');
	const guard = open.indexOf('requestId !== pluginEditorLoadRequestId');
	const write = open.indexOf('pluginEditorContent = content');
	assert.ok(awaited >= 0 && guard > awaited && write > guard);
	assert.match(region('function closePluginEditor', 'async function savePluginEditor'), /pluginEditorLoadRequestId \+= 1/);
});

test('plugin file-read failures are shown and always release the action lock', () => {
	const change = region('async function onPluginFileChange', 'async function openPluginEditor');
	assert.match(change, /try \{[\s\S]*await file\.text\(\)/);
	assert.match(change, /catch \(cause\) \{[\s\S]*pluginSectionReasons/);
	assert.match(change, /finally \{[\s\S]*pluginBusy = false/);
});
