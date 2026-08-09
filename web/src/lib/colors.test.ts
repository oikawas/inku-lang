// Run with: npm run test:unit  (node:test, no test dependency)
//
// The nameplate of a work's catalog. Two states a bare lookup cannot express:
// an id that was renamed still names something, and an id that was retired names
// nothing at all. The old code answered `catalogById(...)?.name ?? 'inku Default'`
// to both, which put a catalog on screen that the work was never drawn with.
//
// None of this decides a color. The work is drawn in its own recorded colors; a
// retired nameplate is a fact about the name only.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { catalogNameplate, type ColorCatalog } from './colors.ts';

const catalog = (id: string, name: string): ColorCatalog => ({
	id,
	name,
	sub: '',
	map: {},
	swatches: [],
	palette: []
});

const CATALOGS = [catalog('ink_season', 'Ink Season'), catalog('default', 'inku Default')];
const RENAMED = { japanese: 'ink_season', egyptian: 'desert_mineral' };

test('a catalog that is still here is named and not marked', () => {
	assert.deepEqual(catalogNameplate(CATALOGS, RENAMED, 'ink_season'), {
		name: 'Ink Season',
		retired: false
	});
});

test('a renamed id is shown under the name it answers to today', () => {
	// 57 works carry an id that was renamed out from under them. Before this they
	// showed as 'inku Default' — a catalog none of them was drawn with.
	assert.deepEqual(catalogNameplate(CATALOGS, RENAMED, 'japanese'), {
		name: 'Ink Season',
		retired: false
	});
});

test('an id nothing answers to is marked retired, under the name that was recorded', () => {
	// `egyptian` was renamed to `desert_mineral`, which was then retired: following
	// the rename still arrives nowhere, and the work's own recorded name is the
	// most truthful thing left to show.
	assert.deepEqual(catalogNameplate(CATALOGS, RENAMED, 'egyptian', 'Egyptian'), {
		name: 'Egyptian',
		retired: true
	});
	// With nothing recorded, the id itself — never a catalog it was not drawn with.
	assert.deepEqual(catalogNameplate(CATALOGS, RENAMED, 'sea_stone'), {
		name: 'sea_stone',
		retired: true
	});
});
