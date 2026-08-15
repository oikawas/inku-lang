// Run with: npm run test:unit  (node:test, no test dependency)
//
// `Nature.菖蒲` is not a typo the writer can see. The expansion layer knows
// the namespace and not the name, strips the reference, and takes the whole
// sentence with it -- "twenty of them, side by side" leaves one line on the
// paper. The warning goes to the record. This checks the two places it now
// also goes: the editor while the name is being typed, and the screen after
// the drawing.
//
// The DDL editor is the only caller that holds the list of names the server
// has, so it is the only one whose output may change. The other four calls
// are measured against output frozen at 2f98dbc8, the branch point.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { highlightDDL } from './highlight.ts';
import {
	buildPluginNameIndex,
	pluginWarningsToShow,
	scanPluginReferences,
	unknownPluginNames
} from './plugin-names.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');

// The shape GET /api/saijiki hands the editor, with the entries of
// server/plugins/nature-leaves.inku-plugin.md that these cases need.
const ENTRIES = [
	{
		qualified_name: 'Nature.下草',
		note_ja: '',
		note_en: '',
		fires_on_ja: ['下草', '草むら', '菖蒲', 'あやめ', '燕子花', 'かきつばた', '薄', 'すすき'],
		fires_on_en: ['undergrowth', 'grasses', 'iris leaves', 'kakitsubata', 'pampas grass']
	},
	{
		qualified_name: 'Nature.青葉',
		note_ja: '',
		note_en: '',
		fires_on_ja: ['青葉', '茂み', '枝葉'],
		fires_on_en: ['summer leaves', 'green foliage', 'leafy branch']
	}
];

const INDEX = buildPluginNameIndex(ENTRIES);

const classesIn = (html: string) => [...html.matchAll(/ddl-token-([a-z-]+)/g)].map((m) => m[1]);

// ── T-3 / T-4 / T-6: which references are marked, and which are not ────────

test('T-3: a qualified name the server holds is a plugin token', () => {
	const html = highlightDDL('Nature.青葉が茂る。', null, INDEX);
	assert.match(html, /<span class="ddl-token ddl-token-plugin">Nature\.青葉<\/span>/);
	assert.ok(!classesIn(html).includes('unknown'), html);
});

test('T-4: a qualified name the server does not hold gets its own class', () => {
	for (const text of ['Nature.菖蒲', 'Garden.石灯籠']) {
		const html = highlightDDL(text, null, INDEX);
		assert.match(html, new RegExp(`<span class="ddl-token ddl-token-unknown">${text}</span>`));
	}
});

test('T-4: an unknown namespace is caught, not only an unknown word', () => {
	// `Garden` is nobody's namespace here. Judging by namespace alone -- the
	// way the old `case 'Nature'` did -- would let it through unmarked.
	const references = scanPluginReferences('Garden.石灯籠を三つ置く。', INDEX);
	assert.equal(references.length, 1);
	assert.equal(references[0].known, false);
	// The mark runs to the full stop because the server's pattern does: what
	// is marked is the extent the expansion layer reads as the reference, and
	// that whole sentence is what it removes.
	assert.equal(references[0].text, 'Garden.石灯籠を三つ置く');
});

test('T-6: a bare unknown word keeps the colour it has today', () => {
	// Only a dotted reference is stripped by the expansion layer; a plain
	// unknown word reaches Stage 2 and is read there.
	for (const text of ['菖蒲を二十本並べる。', 'ジャバウォックを三つ置く。細い線。', '0.5 の比率']) {
		assert.equal(highlightDDL(text, null, INDEX), highlightDDL(text));
	}
});

test('T-6: the pattern is the server’s own, down to the capital letter', () => {
	// document_format.py:60 requires [A-Z] after a non-word character.
	assert.deepEqual(scanPluginReferences('nature.下草', INDEX), []);
	assert.deepEqual(scanPluginReferences('0.5 の比率で薄墨を置く。', INDEX), []);
});

test('a known name ends where the name ends, and what follows is scanned again', () => {
	const html = highlightDDL('Nature.下草と菖蒲', null, INDEX);
	assert.match(html, /<span class="ddl-token ddl-token-plugin">Nature\.下草<\/span>と菖蒲$/);
	const behind = scanPluginReferences('Nature.下草Garden.石灯籠', INDEX);
	assert.deepEqual(
		behind.map((reference) => [reference.text, reference.known]),
		[['Nature.下草', true], ['Garden.石灯籠', false]]
	);
});

// ── T-5: the guidance ──────────────────────────────────────────────────────

test('T-5: a firing phrase is named, and a name nobody claims is not', () => {
	const [iris] = unknownPluginNames('Nature.菖蒲を二十本並べる', INDEX);
	assert.equal(iris.namespace, 'Nature');
	assert.equal(iris.firesAs, '下草', 'the phrase 菖蒲 belongs to Nature.下草');

	const [lantern] = unknownPluginNames('Garden.石灯籠', INDEX);
	assert.equal(lantern.firesAs, null, 'no entry claims 石灯籠');
});

test('T-5: the English phrases fire too, and each name is listed once', () => {
	const [grasses] = unknownPluginNames('Nature.grasses stand low.', INDEX);
	assert.equal(grasses.firesAs, '下草');
	assert.equal(unknownPluginNames('Nature.菖蒲。Nature.菖蒲。', INDEX).length, 1);
});

// ── T-7: the four callers that hand over no index ──────────────────────────

// 2026-08-12, ddl-engine 15: the saijiki gained おもて / surfaces, and 薄墨 is
// one of its eleven words. The editor paints a saijiki word wherever it stands,
// so the four frozen cases that spell 薄墨 now wrap it -- a consequence of the
// vocabulary growing, not of the plugin-name index this contract added. The
// fixture is declared, not rebaked: unwinding this one substitution has to
// reproduce the frozen bytes exactly, so any other drift still fails.
// 2026-08-14, ddl-engine 19: the saijiki gained じ / grounds, and `paper` is
// one of its seven words. Same shape as 薄墨 above -- the vocabulary grew, the
// plugin-name index did not move -- and declared the same way rather than
// rebaked, so any drift that is not this substitution still fails.
const DECLARED_SUBSTITUTIONS: readonly [RegExp, string][] = [
	[/<span class="ddl-token ddl-token-word">薄墨<\/span>/g, '薄墨'],
	[/<span class="ddl-token ddl-token-word">paper<\/span>/g, 'paper']
];

test('T-7: without the index the output is byte-identical to the branch point', () => {
	const frozen = JSON.parse(
		read('fixtures/highlight-without-plugin-names.2f98dbc8.json')
	) as Record<string, string>;
	assert.ok(Object.keys(frozen).length >= 60, 'the frozen corpus is thinner than it was');
	let declared = 0;
	for (const [key, expected] of Object.entries(frozen)) {
		const [text, caret] = JSON.parse(key) as [string, number | null];
		const actual = highlightDDL(text, caret);
		if (actual === expected) continue;
		const unwound = DECLARED_SUBSTITUTIONS.reduce(
			(html, [pattern, plain]) => html.replace(pattern, plain),
			actual
		);
		assert.equal(unwound, expected, `changed for ${key}`);
		declared += 1;
	}
	assert.equal(declared, 8, 'the declared substitutions cover eight cases, no more and no fewer');
});

test('T-7: the four callers pass no index, and the editor passes one', () => {
	const viewer = read('components/DdlViewer.svelte');
	assert.match(viewer, /highlightDDL\(primary\)/);
	assert.match(viewer, /highlightDDL\(expandedDdl \?\? ''\)/);
	const page = read('../routes/+page.svelte');
	assert.match(page, /highlightDDL\(batchActiveDdl\)/);
	assert.match(page, /highlightDDL\(demoGeneratedDdl\)/);
	const dialog = read('components/DdlEditorDialog.svelte');
	assert.match(dialog, /highlightDDL\(value, [^)]*, pluginNameIndex\)/);
});

// ── T-8 / T-9: after the drawing ───────────────────────────────────────────

test('T-8: the warnings a drawing carries are the ones shown', () => {
	const warnings = ['stray non-core reference removed from 1 sentence(s); expansion kept'];
	assert.deepEqual(pluginWarningsToShow({ plugin_warnings: warnings }), warnings);
});

test('T-9: nothing to say means nothing on screen', () => {
	assert.deepEqual(pluginWarningsToShow({ plugin_warnings: [] }), []);
	assert.deepEqual(pluginWarningsToShow({}), []);
	assert.deepEqual(pluginWarningsToShow(null), []);
	assert.deepEqual(pluginWarningsToShow({ plugin_warnings: ['   '] }), []);
});

test('T-8/T-9: the page reads the response and hides the empty frame', () => {
	const page = read('../routes/+page.svelte');
	assert.match(page, /pluginWarningsShown = \$derived\(pluginWarningsToShow\(result\)\)/);
	assert.match(page, /\{#if pluginWarningsShown\.length > 0 && inputMode === 'single'\}/);
	assert.match(page, /\{#each pluginWarningsShown as warning\}/);
	assert.match(page, /plugin_warnings\?: string\[\] \| null;/, 'the response field is typed');
});

// ── T-10 / T-11: the colour ────────────────────────────────────────────────

const TOKENS = ['--ddl-token-unknown-fg', '--ddl-token-unknown-bg', '--ddl-token-unknown-border'];

function tokenValues(block: string): Record<string, string> {
	const values: Record<string, string> = {};
	for (const token of TOKENS) {
		const match = block.match(new RegExp(`${token}:\\s*([^;]+);`));
		if (match) values[token] = match[1].trim();
	}
	return values;
}

function themeBlocks(): { light: string; dark: string } {
	const page = read('../routes/+page.svelte');
	const lightAt = page.indexOf(':global(:root) {');
	const darkAt = page.indexOf(":global(html[data-theme='dark']) {");
	assert.ok(lightAt >= 0 && darkAt > lightAt);
	return {
		light: page.slice(lightAt, darkAt),
		dark: page.slice(darkAt, page.indexOf('\n\t}', darkAt))
	};
}

test('T-10: the new colour is a :root token, not a literal in the rule', () => {
	const page = read('../routes/+page.svelte');
	const rule = page.slice(page.indexOf(':global(.ddl-token-unknown)'));
	const body = rule.slice(0, rule.indexOf('}') + 1);
	for (const token of TOKENS.slice(0, 2)) assert.match(body, new RegExp(`var\\(${token}\\)`));
	assert.ok(!/#fff\b|#ffffff\b|\bwhite\b/i.test(body), body);
	assert.ok(!/:\s*\d+px/.test(body.replace(/text-underline-offset:[^;]+;/, '')), body);

	const dialog = read('components/DdlEditorDialog.svelte');
	const strip = dialog.slice(dialog.indexOf('.ddl-unknown-names {'), dialog.indexOf('.ddl-unknown-hint'));
	assert.ok(!/#fff\b|#ffffff\b|\bwhite\b/i.test(strip), strip);
	for (const token of TOKENS) assert.match(strip + dialog, new RegExp(`var\\(${token}\\)`));
});

/** WCAG relative luminance of a #rrggbb colour. */
function luminance(hex: string): number {
	const value = hex.replace('#', '');
	const channels = [0, 2, 4].map((at) => parseInt(value.slice(at, at + 2), 16) / 255);
	const linear = channels.map((c) => (c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4));
	return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2];
}

function contrast(a: string, b: string): number {
	const [high, low] = [luminance(a), luminance(b)].sort((x, y) => y - x);
	return (high + 0.05) / (low + 0.05);
}

test('T-11: the mark is readable on the editor’s paper in both themes', () => {
	// The editor's background is var(--panel). Measured, not eyeballed: a
	// value that reads well in light can sink into the dark panel.
	const { light, dark } = themeBlocks();
	const panelLight = light.match(/--panel:\s*(#[0-9a-f]{6})/i)![1];
	const panelDark = dark.match(/--panel:\s*(#[0-9a-f]{6})/i)![1];
	const lightFg = tokenValues(light)['--ddl-token-unknown-fg'];
	const darkFg = tokenValues(dark)['--ddl-token-unknown-fg'];
	assert.match(lightFg, /^#[0-9a-f]{6}$/i);
	assert.match(darkFg, /^#[0-9a-f]{6}$/i);
	assert.ok(
		contrast(lightFg, panelLight) >= 4.5,
		`light theme contrast ${contrast(lightFg, panelLight).toFixed(2)} against ${panelLight}`
	);
	assert.ok(
		contrast(darkFg, panelDark) >= 4.5,
		`dark theme contrast ${contrast(darkFg, panelDark).toFixed(2)} against ${panelDark}`
	);
	// And it is not the red of an error: a name absent today can be installed
	// tomorrow, so the two must not share a colour.
	assert.notEqual(lightFg.toLowerCase(), light.match(/--danger:\s*(#[0-9a-f]{6})/i)![1].toLowerCase());
});
