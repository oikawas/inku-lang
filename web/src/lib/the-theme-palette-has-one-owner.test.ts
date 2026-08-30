// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/the-theme-palette-has-one-owner.test.ts
import assert from 'node:assert/strict';
import { existsSync, readFileSync, readdirSync } from 'node:fs';
import { dirname, extname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const LIB_DIR = dirname(fileURLToPath(import.meta.url));
const WEB_SRC = join(LIB_DIR, '..');
const THEME_PATH = join(WEB_SRC, 'routes', '+page.svelte');

function read(path: string): string {
	return readFileSync(path, 'utf8');
}

function blockAfter(css: string, marker: string): string {
	const markerAt = css.indexOf(marker);
	assert.ok(markerAt >= 0, `missing theme selector ${marker}`);
	const openAt = css.indexOf('{', markerAt);
	const closeAt = css.indexOf('}', openAt);
	assert.ok(openAt >= 0 && closeAt > openAt, `missing theme block for ${marker}`);
	return css.slice(openAt + 1, closeAt);
}

function tokenValues(block: string): Map<string, string> {
	return new Map(
		[...block.matchAll(/(--[a-z0-9-]+)\s*:\s*([^;]+);/gi)].map((match) => [match[1], match[2].trim()])
	);
}

function sourceFiles(root: string): string[] {
	return readdirSync(root, { withFileTypes: true }).flatMap((entry) => {
		const path = join(root, entry.name);
		if (entry.isDirectory()) return sourceFiles(path);
		return ['.svelte', '.css'].includes(extname(entry.name)) ? [path] : [];
	});
}

function luminance(hex: string): number {
	const channels = [1, 3, 5].map((at) => parseInt(hex.slice(at, at + 2), 16) / 255);
	const linear = channels.map((channel) => channel <= 0.03928
		? channel / 12.92
		: ((channel + 0.055) / 1.055) ** 2.4);
	return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(a: string, b: string): number {
	const [high, low] = [luminance(a), luminance(b)].sort((left, right) => right - left);
	return (high + 0.05) / (low + 0.05);
}

test('T-1  one canonical palette supplies distinct accessible tooltip themes', () => {
	assert.ok(existsSync(THEME_PATH), '+page.svelte must own the application palette');
	const theme = read(THEME_PATH);
	assert.match(theme, /Application color contract/);

	const light = tokenValues(blockAfter(theme, "html[data-theme='light']"));
	const dark = tokenValues(blockAfter(theme, "html[data-theme='dark']"));
	assert.deepEqual([...light.keys()].sort(), [...dark.keys()].sort(), 'light and dark token sets drifted');

	for (const values of [light, dark]) {
		for (const token of ['--tooltip-bg', '--tooltip-fg', '--tooltip-muted', '--tooltip-border', '--tooltip-shadow']) {
			assert.ok(values.has(token), `${token} is missing from a theme`);
		}
	}
	const lightBg = light.get('--tooltip-bg')!;
	const lightFg = light.get('--tooltip-fg')!;
	const darkBg = dark.get('--tooltip-bg')!;
	const darkFg = dark.get('--tooltip-fg')!;
	for (const value of [lightBg, lightFg, darkBg, darkFg]) assert.match(value, /^#[0-9a-f]{6}$/i);
	assert.ok(luminance(lightBg) > luminance(darkBg), 'light and dark tooltips still use the same dark plate');
	assert.ok(contrast(lightBg, lightFg) >= 4.5, 'light tooltip contrast is below 4.5:1');
	assert.ok(contrast(darkBg, darkFg) >= 4.5, 'dark tooltip contrast is below 4.5:1');

	for (const token of light.keys()) {
		const definition = new RegExp(`${token.replaceAll('-', '\\-')}\\s*:`);
		const otherOwners = sourceFiles(WEB_SRC)
			.filter((path) => path !== THEME_PATH && definition.test(read(path)));
		assert.deepEqual(otherOwners, [], `${token} has another owner`);
	}

	for (const relativePath of ['components/Tooltip.svelte', 'components/ModelMetaCard.svelte', 'components/ModelCardPicker.svelte']) {
		const source = read(join(LIB_DIR, relativePath));
		assert.match(source, /var\(--tooltip-bg\)/);
		assert.match(source, /var\(--tooltip-fg\)/);
		assert.match(source, /var\(--tooltip-border\)/);
		assert.match(source, /var\(--tooltip-shadow\)/);
		assert.doesNotMatch(source, /#111820|#f8fafc|#cbd5e1|#64748b/i);
	}
});
