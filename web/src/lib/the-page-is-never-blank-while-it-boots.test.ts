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

function pageRuleFor(selectorPattern: string): string {
	const match = page.match(new RegExp(`${selectorPattern}\\s*\\{([^}]*)\\}`));
	assert.ok(match, `missing page CSS rule for ${selectorPattern}`);
	return match[1];
}

/**
 * The ground colour the app itself declares for the dark theme.  Read it rather
 * than restating it: a copy here would have to be edited by hand every time the
 * token moves, and the shell would be free to drift until someone noticed.
 */
function canonicalDarkBackground(): string {
	const darkTheme = page.match(/:global\(html\[data-theme='dark'\]\)\s*\{([\s\S]*?)\n\s*\}/)?.[1];
	assert.ok(darkTheme, 'the canonical dark theme is missing');
	const background = darkTheme.match(/--bg:\s*(#[0-9a-fA-F]{6})\s*;/)?.[1];
	assert.ok(background, 'the canonical dark background is missing');
	return background;
}

function backgroundOf(selectorPattern: string): string | undefined {
	return ruleFor(selectorPattern).match(/(?:^|;)\s*background:\s*(#[0-9a-fA-F]{6})\s*;/)?.[1];
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
	assert.equal(backgroundOf('html,\\s*body'), canonicalDarkBackground());
});

// ── T-32 ────────────────────────────────────────────────────────────────────
test('T-32  main dismisses the boot curtain without JavaScript', () => {
	const dismissal = ruleFor('body:has\\(main\\) #boot-curtain');
	assert.match(dismissal, /(?:^|;)\s*display:\s*none\s*;/);
	assert.doesNotMatch(app, /<script\b/i);
});

// ── T-33 ────────────────────────────────────────────────────────────────────
test('T-33  the boot curtain uses the canonical dark background', () => {
	assert.equal(backgroundOf('#boot-curtain'), canonicalDarkBackground());
});

// ── T-34 ────────────────────────────────────────────────────────────────────
test('T-34  the mounted app paints over the dark boot ground with the active theme', () => {
	const rootRule = pageRuleFor('\\.root');
	assert.match(rootRule, /(?:^|;)\s*background:\s*var\(--bg\)\s*;/);
	assert.match(rootRule, /(?:^|;)\s*color:\s*var\(--fg\)\s*;/);
});

// ── T-35 ────────────────────────────────────────────────────────────────────
test('T-35  the input-mode panel paints its own active-theme surface', () => {
	const panelRule = pageRuleFor('\\.left-panel');
	assert.match(panelRule, /(?:^|;)\s*background:\s*var\(--bg\)\s*;/);
	assert.match(panelRule, /(?:^|;)\s*color:\s*var\(--fg\)\s*;/);
});
