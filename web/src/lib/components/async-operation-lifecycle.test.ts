import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (name: string): string => readFileSync(new URL(`./${name}`, import.meta.url), 'utf8');

test('AI refinement aborts work and stops its elapsed owner when destroyed', () => {
	const source = read('AIRefineModal.svelte');
	assert.match(
		source,
		/onDestroy\(\(\) => \{[\s\S]*?abortController\?\.abort\(\);[\s\S]*?refineElapsed\.stop\(\);[\s\S]*?\}\);/
	);
});

test('the DDL editor aborts its active draw when destroyed', () => {
	const source = read('DdlEditorDialog.svelte');
	assert.match(source, /import \{[^}]*onDestroy[^}]*\} from 'svelte';/);
	assert.match(source, /onDestroy\(\(\) => drawController\?\.abort\(\)\);/);
});

test('the dynamic lineage panel releases draw controllers and its copy timer', () => {
	const source = read('LineagePanel.svelte');
	const mount = source.indexOf('\n\tonMount(() => {');
	const cleanupStart = source.indexOf('\n\t\treturn () => {', mount);
	const cleanupEnd = source.indexOf('\n\t\t};', cleanupStart);
	assert.ok(mount >= 0 && cleanupStart > mount && cleanupEnd > cleanupStart);
	const cleanup = source.slice(cleanupStart, cleanupEnd);
	assert.match(cleanup, /sketchDrawController\?\.abort\(\)/);
	assert.match(cleanup, /editDrawController\?\.abort\(\)/);
	assert.match(cleanup, /clearTimeout\(copiedHashTimer\)/);
});
