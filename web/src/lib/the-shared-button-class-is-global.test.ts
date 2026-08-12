// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { readFileSync, readdirSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const COMPONENT_DIR = new URL('./components/', import.meta.url);

test('T-27: ghost buttons have one global base rule and no scoped copies', () => {
	const page = read('../routes/+page.svelte');
	const baseRules = [...page.matchAll(/:global\(\.ghost-btn\)\s*\{([^}]*)\}/g)];
	assert.equal(baseRules.length, 1);

	const base = baseRules[0][1];
	for (const token of ['--btn-sm-padding', '--btn-sm-radius', '--btn-sm-font-size']) {
		assert.match(base, new RegExp(`var\\(${token}\\)`), token);
	}
	for (const token of ['--panel', '--fg2', '--border2']) {
		assert.match(base, new RegExp(`var\\(${token}\\)`), token);
	}
	assert.match(page, /:global\(\.ghost-btn:hover:not\(:disabled\)\)/);
	assert.match(page, /:global\(\.ghost-btn:disabled\)/);
	assert.match(page, /:global\(\.ghost-btn\.ghost-active\)/);

	let users = 0;
	for (const name of readdirSync(COMPONENT_DIR).filter((entry) => entry.endsWith('.svelte'))) {
		const source = read(`./components/${name}`);
		if (/class="[^"]*\bghost-btn\b/.test(source)) users += 1;
		assert.doesNotMatch(source, /^\s*\.ghost-btn(?:[.:\w()-]+)?\s*\{/m, name);
	}
	assert.ok(users > 1, 'the shared rule has fewer than two component users');
});

test('T-27: plugin chips share one global accent rule', () => {
	const page = read('../routes/+page.svelte');
	const rules = [...page.matchAll(/:global\(\.saijiki-chip\.plugin-chip\)\s*\{([^}]*)\}/g)];
	assert.equal(rules.length, 1);
	assert.match(rules[0][1], /var\(--accent\)/);
	assert.match(rules[0][1], /var\(--accent-light\)/);

	for (const name of ['SaijikiDrawer.svelte', 'SaijikiInline.svelte']) {
		const source = read(`./components/${name}`);
		assert.match(source, /class="saijiki-chip plugin-chip"/, name);
		assert.doesNotMatch(source, /\.saijiki-chip\.plugin-chip\s*\{/, name);
	}
});
