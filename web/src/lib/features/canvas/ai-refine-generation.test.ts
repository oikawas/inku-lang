// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { ddlGenerationSeeds } from './ai-refine-generation.ts';

test('a generation drawn from DDL changes only the seed its kind is about', () => {
	const parent = { renderSeed: '1553303611486672067', compositionSeed: 7 };
	const fresh = () => 42;
	assert.deepEqual(ddlGenerationSeeds('layout_change', parent, fresh), { renderSeed: '1553303611486672067', compositionSeed: 42 });
	assert.deepEqual(ddlGenerationSeeds('catalog_change', parent, fresh), { renderSeed: '1553303611486672067', compositionSeed: 7 });
	// Zero is a seed: a layout keeps it as the performance.
	assert.deepEqual(ddlGenerationSeeds('layout_change', { renderSeed: 0, compositionSeed: null }, fresh), { renderSeed: 0, compositionSeed: 42 });
});
