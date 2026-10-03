import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';
import { compile, parse } from 'svelte/compiler';
import { render } from 'svelte/server';

test('ChatGPT has its own category and never includes the appearance settings body', async () => {
	const source = readFileSync(new URL('../../components/SettingsModal.svelte', import.meta.url), 'utf8');
	const ast = parse(source, { modern: true });
	let body: any;
	const components: any[] = [];
	function walk(node: any) {
		if (!node || typeof node !== 'object') return;
		if (node.type === 'RegularElement' && node.attributes?.some((a: any) => a.name === 'class' && a.value?.some((v: any) => v.data === 'settings-body'))) body = node;
		if (node.type === 'Component') components.push(node);
		for (const value of Object.values(node)) {
			if (Array.isArray(value)) value.forEach(walk);
			else if (value && typeof value === 'object') walk(value);
		}
	}
	walk(ast.fragment);
	assert.ok(body);
	const start = body.fragment.nodes[0].start;
	const end = body.fragment.nodes.at(-1).end;
	let fragment = source.slice(start, end);
	for (const node of components.filter((n) => n.start >= start && n.end <= end).sort((a, b) => b.start - a.start)) {
		fragment = fragment.slice(0, node.start - start) + `<span data-view="${node.name}"></span>` + fragment.slice(node.end - start);
	}
	const harness = `<script lang="ts">let { settingsTab } = $props(); const reaches = () => true; const appearanceSection = 'display'; const exportSection = 'files';</script>${fragment}`;
	const code = compile(harness, { generate: 'server', filename: 'settings-body.svelte' }).js.code
		.replace(/(['"])svelte\/internal\/server\1/g, JSON.stringify(import.meta.resolve('svelte/internal/server')));
	const component = (await import('data:text/javascript;base64,' + Buffer.from(code).toString('base64'))).default;
	const chatgpt = render(component, { props: { settingsTab: 'chatgpt' } }).body;
	assert.match(chatgpt, /data-view="ChatGPTSettings"/);
	assert.doesNotMatch(chatgpt, /data-view="AppearanceSettings"/);
	const appearance = render(component, { props: { settingsTab: 'misc' } }).body;
	assert.match(appearance, /data-view="AppearanceSettings"/);
	assert.doesNotMatch(appearance, /data-view="ChatGPTSettings"/);
	const category = source.slice(source.indexOf("{#if reaches('chatgpt')}"), source.indexOf("{/if}", source.indexOf("{#if reaches('chatgpt')}")));
	assert.match(category, /<section class="settings-category">/);
});
