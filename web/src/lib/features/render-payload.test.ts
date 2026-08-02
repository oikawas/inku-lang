// Run with: npm run test:unit  (node:test, no test dependency)
//
// The gate for the render payload registry.  It asserts two things the type
// checker cannot: that every feature which reaches the server is still
// contributing, and that each one still emits the fields its endpoints expect.
//
// It reads the real contributors, not stand-ins: dropping a feature's
// registerRenderContributor call turns this file red and nothing else.
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { renderContributorIds, renderSettingsPayload } from './render-payload.ts';
import { bindColorCatalogRenderState, colorCatalogContributor, colorCatalogOverride } from './color-catalog/render.ts';
import { bindTenkeiRenderState, tenkeiContributor, tenkeiOverride } from './tenkei/render.ts';
import { bindWildRenderState, wildContributor, wildOverride } from './wild/render.ts';

// Stand in for the runes the settings modules own, so the live-value path is
// exercised with values distinguishable from the defaults.
bindColorCatalogRenderState(() => 'live-catalog');
bindTenkeiRenderState(() => 'sparse');
bindWildRenderState(() => true);

// Every feature that reaches the server.  Sorted, because the collected payload
// must not depend on the order the features registered in.
const EXPECTED_CONTRIBUTORS = ['color-catalog', 'tenkei', 'wild'];

test('every feature that reaches the server is contributing', () => {
	assert.deepEqual([...renderContributorIds()].sort(), EXPECTED_CONTRIBUTORS);
	assert.equal(renderContributorIds().length, EXPECTED_CONTRIBUTORS.length);
});

test('a fresh paint states every feature, from the live settings', () => {
	assert.deepEqual(renderSettingsPayload('paint'), {
		catalog_id: 'live-catalog',
		catalog_mode: 'fixed',
		tenkei: 'sparse',
		wild: true
	});
});

test('a compose inherits the level and the switch unless told otherwise', () => {
	assert.deepEqual(renderSettingsPayload('compose'), { catalog_id: 'live-catalog' });
});

test('a re-render of a stored score carries no level and no mode', () => {
	assert.deepEqual(renderSettingsPayload('render-svg'), { catalog_id: 'live-catalog' });
	assert.deepEqual(renderSettingsPayload('render-score'), { catalog_id: 'live-catalog' });
});

test('an override replaces the live value without naming a request field', () => {
	assert.deepEqual(renderSettingsPayload('paint', colorCatalogOverride('frozen', 'auto')), {
		catalog_id: 'frozen',
		catalog_mode: 'auto',
		tenkei: 'sparse',
		wild: true
	});
});

test('a null override omits the field, which is how inheriting is expressed', () => {
	assert.deepEqual(renderSettingsPayload('paint', { ...tenkeiOverride(null), ...wildOverride(false) }), {
		catalog_id: 'live-catalog',
		catalog_mode: 'fixed',
		wild: false
	});
	assert.deepEqual(renderSettingsPayload('compose', wildOverride(null)), { catalog_id: 'live-catalog' });
});

test('a stored score can be re-rendered with the switch it was drawn with', () => {
	assert.deepEqual(renderSettingsPayload('render-svg', { ...colorCatalogOverride('c'), ...wildOverride(false) }), {
		catalog_id: 'c',
		wild: false
	});
});

test('contributors own disjoint fields, so order cannot decide the payload', () => {
	// If two features claimed the same field, whichever registered last would
	// win and the order would start to matter.  Counting the slices catches it.
	const slices = [colorCatalogContributor, tenkeiContributor, wildContributor]
		.map((contributor) => contributor.payload('paint', undefined));
	const fieldTotal = slices.reduce((total, slice) => total + Object.keys(slice).length, 0);
	assert.equal(Object.keys(renderSettingsPayload('paint')).length, fieldTotal);
});
