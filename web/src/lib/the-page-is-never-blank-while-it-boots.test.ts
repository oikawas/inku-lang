// Run with: npm run test:unit  (node:test, no DOM dependency)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const LIB_DIR = dirname(fileURLToPath(import.meta.url));
const WEB_SRC = join(LIB_DIR, '..');
const app = readFileSync(join(WEB_SRC, 'app.html'), 'utf8');
const page = readFileSync(join(WEB_SRC, 'routes', '+page.svelte'), 'utf8');

function ruleFor(selectorPattern: string): string {
	const match = app.match(new RegExp(`${selectorPattern}\\s*\\{([^}]*)\\}`));
	assert.ok(match, `missing CSS rule for ${selectorPattern}`);
	return match[1];
}

// ── T-30 ────────────────────────────────────────────────────────────────────
test('T-30  the boot curtain precedes the app and covers the viewport', () => {
	const curtainAt = app.indexOf('<div id="boot-curtain">');
	const appAt = app.indexOf('%sveltekit.body%');
	assert.ok(curtainAt >= 0, 'the boot curtain is missing');
	assert.ok(curtainAt < appAt, 'the boot curtain must precede the SvelteKit body');

	const curtainRule = ruleFor('#boot-curtain');
	assert.match(curtainRule, /(?:^|;)\s*position:\s*fixed\s*;/);
	assert.match(curtainRule, /(?:^|;)\s*inset:\s*0\s*;/);
});

// ── T-31 ────────────────────────────────────────────────────────────────────
test('T-31  the boot curtain is styled inline without a stylesheet request', () => {
	const head = app.match(/<head>([\s\S]*?)<\/head>/)?.[1] ?? '';
	assert.match(head, /<style>[\s\S]*#boot-curtain\s*\{/);
	assert.doesNotMatch(app, /<link\b[^>]*\brel=["']stylesheet["']/i);
	assert.match(ruleFor('html,\\s*body'), /(?:^|;)\s*background:\s*#171716\s*;/);
});

// ── T-32 ────────────────────────────────────────────────────────────────────
test('T-32  main dismisses the boot curtain without JavaScript', () => {
	const dismissal = ruleFor('body:has\\(main\\) #boot-curtain');
	assert.match(dismissal, /(?:^|;)\s*display:\s*none\s*;/);
	assert.doesNotMatch(app, /<script\b/i);
});

// ── T-33 ────────────────────────────────────────────────────────────────────
test('T-33  the boot curtain uses the canonical dark background', () => {
	const darkTheme = page.match(/:global\(html\[data-theme='dark'\]\)\s*\{([\s\S]*?)\n\s*\}/)?.[1];
	assert.ok(darkTheme, 'the canonical dark theme is missing');
	const canonicalBackground = darkTheme.match(/--bg:\s*(#[0-9a-fA-F]{6})\s*;/)?.[1];
	assert.ok(canonicalBackground, 'the canonical dark background is missing');

	const curtainBackground = ruleFor('#boot-curtain').match(/(?:^|;)\s*background:\s*(#[0-9a-fA-F]{6})\s*;/)?.[1];
	assert.equal(curtainBackground, canonicalBackground);
});
