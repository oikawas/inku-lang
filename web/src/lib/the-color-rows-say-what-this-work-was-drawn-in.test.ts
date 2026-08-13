// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the two colour rows in the generation info drawer.
//
// The drawer had a "what the catalog holds" row that printed a tagline fixed on
// the catalog, so it said nothing about the work: "Lantern & Dew" already tells
// the reader what "night air, lantern, dew" tells them. It is gone (author
// decision, 2026-08-13), and so is the reader that had localised it.
//
// What the drawer never showed is the one colour fact that belongs to the work
// rather than to the catalog: which colour each colour word was actually drawn
// in. `statusCatalogName` already read that map to decide whether to say "no
// record", and then threw it away.
//
// T-41 (the tagline is gone, the catalog name is not), T-42 (the map is the nine
// colour words and not the catalog's palette), T-43 (the drawer shows it, and an
// absent map is not an empty one).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { COLOR_KEY_ORDER, colorMapEntries, colorWordLabel } from './colors.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const PANEL = read('./components/CanvasPanel.svelte');

// ------------------------------------------------------------------- T-41

test('T-41  the catalog tagline is not shown; the name already said it', () => {
	// Author decision, 2026-08-13. The tagline is a constant of the catalog --
	// "Lantern & Dew" already tells the reader what "night air, lantern, dew"
	// tells them -- so the row said nothing about this work. The reader that
	// localised it went with it rather than being left with no reader.
	assert.doesNotMatch(PANEL, /detailCatalogSub/);
	assert.doesNotMatch(PANEL, /render_color_catalog_sub/);
	assert.doesNotMatch(PANEL, /catalogSubLine/);
	assert.doesNotMatch(read('./colors.ts'), /catalogSubLine/);
	for (const key of ['provenanceLabelCatalogSub', 'provenanceHintCatalogSub']) {
		for (const pack of ['./i18n/ja.ts', './i18n/en.ts', './i18n/types.ts']) {
			assert.doesNotMatch(read(pack), new RegExp(key), `${pack} still carries ${key}`);
		}
	}
});

test('T-41  and the catalog name it stood under is still there', () => {
	// Which of the fourteen catalogs translated the colours is the fact that is
	// about this work, and it stays.
	assert.match(PANEL, /t\(\)\.provenanceHintCatalog\)/);
	assert.match(PANEL, /<dd>\{statusCatalogName\}<\/dd>/);
});

// ------------------------------------------------------------------- T-42

test('T-42  the map is the colour words, not the catalog palette', () => {
	// render_color_map carries a palette:<name> entry per palette colour as well
	// (color_catalogs.py builds it that way). Those are the catalog's list, keyed
	// by an English display name, and they are not what this row answers.
	const entries = colorMapEntries({
		white: '#fffffb',
		black: '#141210',
		'palette:Night Air': '#1b2a3a',
		'palette:Dew White': '#eef3f2'
	} as never);
	assert.deepEqual(entries, [
		{ key: 'white', code: '#fffffb' },
		{ key: 'black', code: '#141210' }
	]);
});

test('T-42  the words come out in saijiki order, and only the ones carried', () => {
	const full = Object.fromEntries(COLOR_KEY_ORDER.map((key) => [key, '#000000']));
	assert.deepEqual(
		colorMapEntries(full).map((entry) => entry.key),
		COLOR_KEY_ORDER
	);
	assert.deepEqual(colorMapEntries({ red: '#a2342a' }), [{ key: 'red', code: '#a2342a' }]);
});

test('T-42  no map recorded is an empty list, not a list of defaults', () => {
	assert.deepEqual(colorMapEntries(null), []);
	assert.deepEqual(colorMapEntries(undefined), []);
	assert.deepEqual(colorMapEntries({}), []);
});

test('T-42  the Japanese word is the saijiki word, not a gloss', () => {
	const ja = COLOR_KEY_ORDER.map((key) => colorWordLabel(key, true));
	assert.deepEqual(ja, ['白', '黒', '青', '赤', '緑', '灰', '黄', '橙', '紫']);
	// English is the key itself, which is the English saijiki word.
	assert.deepEqual(COLOR_KEY_ORDER.map((key) => colorWordLabel(key, false)), COLOR_KEY_ORDER);
	// A key the table does not know is shown as it stands rather than dropped.
	assert.equal(colorWordLabel('palette:Night Air', true), 'palette:Night Air');
});

// ------------------------------------------------------------------- T-43

test('T-43  the map row is shown only when the work carries one', () => {
	assert.match(PANEL, /\{#if detailColorMap\.length > 0\}/);
	assert.match(
		PANEL,
		/colorMapEntries\(statusHistoryItem\?\.render_color_map \?\? result\?\.render_color_map\)/
	);
	assert.match(PANEL, /colorWordLabel\(entry\.key, isJapanese\)/);
	// A chip carries its own hex, so the exact colour is one hover away.
	assert.match(PANEL, /title=\{entry\.code\}/);
});

test('T-43  and the drawer no longer asks for what only that line needed', () => {
	// The catalog table and the rename table were passed in for the sub line.
	// A prop nothing reads is a prop that goes stale without anything saying so.
	assert.doesNotMatch(PANEL, /colorCatalogs/);
	assert.doesNotMatch(PANEL, /renamedCatalogIds/);
});
