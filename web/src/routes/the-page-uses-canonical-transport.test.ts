// Run with: npm run test:unit  (node:test, no DOM dependency)
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const PAGE_SOURCE = readFileSync(new URL('./+page.svelte', import.meta.url), 'utf8');

test('the page creates one route-local canonical transport', () => {
	assert.match(
		PAGE_SOURCE,
		/import \{ createApiFetch \} from '\$lib\/transport\/api-fetch';/,
		'the page must import the canonical transport factory'
	);
	assert.equal(
		[...PAGE_SOURCE.matchAll(/\bconst apiFetch = createApiFetch\(\);/g)].length,
		1,
		'the route must create exactly one transport instance'
	);
});

test('the page keeps no transport implementation or compatibility forwarder', () => {
	assert.doesNotMatch(PAGE_SOURCE, /\bRENDER_CAPACITY_RETRIES\b/);
	assert.doesNotMatch(PAGE_SOURCE, /\bfunction delay\s*\(/);
	assert.doesNotMatch(PAGE_SOURCE, /\basync function apiFetch\s*\(/);
	assert.doesNotMatch(PAGE_SOURCE, /export\s+\{[^}]*apiFetch/);
});
