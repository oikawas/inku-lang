// Run with: npm run test:unit  (node:test, no test dependency)
//
// The choice "from the description" has to be reachable, and reachable in one
// place.  There is no component renderer here (test:unit is node:test with no
// DOM), so this reads the sources the way the trash-view gate does: it walks
// the markup for the button and for the checkbox it replaced.
//
// Why a gate at all: the mode used to live on a checkbox in the batch tab and a
// second one in the demo panel.  Folding both into the catalog list is only a
// simplification while the fold stays folded.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { AUTO_CATALOG_ID } from '../features/color-catalog/render.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (name: string) => fs.readFileSync(path.join(here, name), 'utf8');

test('the catalog modal offers the choice, above the catalogs', () => {
	const source = read('ColorCatalogModal.svelte');
	assert.match(source, /onSelectCatalog\(AUTO_CATALOG_ID\)/);
	assert.match(source, /t\(\)\.colorCatalogAuto/);
	// Above: the button comes before the loop over the real catalogs.
	assert.ok(
		source.indexOf('onSelectCatalog(AUTO_CATALOG_ID)') < source.indexOf('{#each catalogs as cat'),
		'the choice must sit above the catalog list'
	);
});

test('the sentinel is one value, named in one place', () => {
	assert.equal(AUTO_CATALOG_ID, 'auto');
	for (const name of ['ColorCatalogModal.svelte', 'BatchPanel.svelte', 'InputPanel.svelte', 'DemoPanel.svelte']) {
		assert.doesNotMatch(read(name), /'auto'/, `${name} must reach the sentinel through AUTO_CATALOG_ID`);
	}
});

test('neither tab keeps a per-tab toggle for it', () => {
	for (const name of ['BatchPanel.svelte', 'DemoPanel.svelte', 'InputPanel.svelte']) {
		const source = read(name);
		assert.doesNotMatch(source, /autoColorCatalog/, `${name} still has the retired toggle`);
		assert.doesNotMatch(source, /catalog_mode/, `${name} still has the retired demo mode`);
	}
});
