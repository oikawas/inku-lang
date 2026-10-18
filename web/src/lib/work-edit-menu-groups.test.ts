// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const MENU = fs.readFileSync(path.join(here, 'components/WorkActionMenu.svelte'), 'utf8');
const markup = MENU.slice(MENU.indexOf('role="menu"'));

test('the work edit menu runs lightest first, in four groups', () => {
	const actions = [...markup.matchAll(/select\('([a-z-]+)', event\)/g)].map((m) => m[1]);
	assert.deepEqual(actions, [
		'color-catalog', 'color-arrangement', 'ground', 'tool',
		'layout', 'instructions',
		'description', 'sketch-grain', 'models',
		'autonomous',
	]);
	const groups = [...markup.matchAll(/role="group" aria-label=\{t\(\)\.(workActionGroup\w+)\}/g)].map((m) => m[1]);
	assert.deepEqual(groups, ['workActionGroupLook', 'workActionGroupForm', 'workActionGroupDescription', 'workActionGroupAi']);
});

test('the items that call the LLM carry its mark, and only those', () => {
	const items = [...markup.matchAll(/select\('([a-z-]+)', event\)\}>\{t\(\)\.\w+\}(\{@render llmMark\(\)\})?<\/button>/g)];
	assert.equal(items.length, 10);
	assert.deepEqual(items.filter((m) => m[2]).map((m) => m[1]), ['description', 'sketch-grain', 'models', 'autonomous']);
});

test('a DDL work hides the description group with its heading', () => {
	assert.match(markup, /\{#if !ddlOrigin\}\s*<div class="work-action-group" role="group" aria-label=\{t\(\)\.workActionGroupDescription\}>/);
	// The arrow keys still walk the items only: the headings are not buttons.
	assert.match(MENU, /menuEl\?\.querySelectorAll<HTMLButtonElement>\('button'\)/);
	assert.doesNotMatch(markup, /<button[^>]*class="work-action-group-label"/);
});

test('each item keeps to one line, the menu widening instead', () => {
	assert.match(MENU, /\.work-action-dropdown > \.work-action-group > button \{ white-space: nowrap; \}/);
});
