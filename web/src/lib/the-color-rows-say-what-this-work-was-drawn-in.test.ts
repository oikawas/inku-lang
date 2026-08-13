// Run with: npm run test:unit  (node:test, no test dependency)
//
// Acceptance for the two colour rows in the generation info drawer.
//
// The drawer had a "what the catalog holds" row that printed the tagline stored
// on the work -- and the server stores catalog["sub"], which is English whatever
// the UI is speaking, so the Japanese drawer read "night air, lantern, dew".
// The Japanese copy exists on the catalog (sub_ja) and the catalog API sends it,
// so the line can be read in the language being read without touching the
// server. Where the definition has moved since the work was drawn, the stored
// line is the historical one and stands as it is.
//
// The drawer also never showed the one colour fact that belongs to the work
// rather than to the catalog: which colour each colour word was actually drawn
// in. `statusCatalogName` already read that map to decide whether to say "no
// record", and then threw it away.
//
// T-41 (the sub line is read in the language being read, and only when it is
// still the same statement), T-42 (the map is the nine colour words and not the
// catalog's palette), T-43 (the drawer shows both, and an absent map is not an
// empty one).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
	COLOR_KEY_ORDER,
	catalogSubLine,
	colorMapEntries,
	colorWordLabel,
	type ColorCatalog
} from './colors.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const PANEL = read('./components/CanvasPanel.svelte');

const CATALOG: ColorCatalog = {
	id: 'lantern_dew',
	name: 'Lantern & Dew',
	sub: 'night air, lantern, dew',
	sub_ja: '夜気、灯火、露',
	map: { white: '#fff', black: '#111' },
	swatches: [],
	palette: []
};

// ------------------------------------------------------------------- T-41

test('T-41  the Japanese drawer reads the Japanese line', () => {
	assert.equal(
		catalogSubLine([CATALOG], {}, 'lantern_dew', 'night air, lantern, dew', true),
		'夜気、灯火、露'
	);
});

test('T-41  the English drawer keeps the line the work carries', () => {
	assert.equal(
		catalogSubLine([CATALOG], {}, 'lantern_dew', 'night air, lantern, dew', false),
		'night air, lantern, dew'
	);
});

test('T-41  a definition that moved since the work was drawn stays historical', () => {
	// The stored line is no longer what the catalog says, so today's Japanese
	// wording would be a different statement, not a translation of this one.
	assert.equal(
		catalogSubLine([CATALOG], {}, 'lantern_dew', 'night air and dew', true),
		'night air and dew'
	);
});

test('T-41  a retired catalog keeps the line too, and a renamed one is followed', () => {
	assert.equal(catalogSubLine([], {}, 'gone', 'some old line', true), 'some old line');
	assert.equal(
		catalogSubLine([CATALOG], { old_id: 'lantern_dew' }, 'old_id', 'night air, lantern, dew', true),
		'夜気、灯火、露'
	);
});

test('T-41  nothing stored means nothing shown, in either language', () => {
	for (const isJapanese of [true, false]) {
		assert.equal(catalogSubLine([CATALOG], {}, 'lantern_dew', '', isJapanese), '');
	}
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

test('T-43  the drawer reads the sub line through the catalog it is shown with', () => {
	assert.match(
		PANEL,
		/catalogSubLine\(colorCatalogs, renamedCatalogIds, detailCatalogId, detailCatalogSubStored, isJapanese\)/
	);
	// And the id comes from the work on screen, not from the current selection.
	assert.match(PANEL, /statusHistoryItem\?\.render_color_catalog_id \?\? result\?\.render_color_catalog_id/);
});

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

test('T-43  the page hands the drawer the catalogs the line needs', () => {
	const page = read('../routes/+page.svelte');
	assert.match(page, /\{colorCatalogs\}/);
	assert.match(page, /\{renamedCatalogIds\}/);
});
