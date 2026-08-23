import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';
import { test } from 'node:test';

const HERE = dirname(fileURLToPath(import.meta.url));
const read = (path: string): string => {
	try { return readFileSync(join(HERE, path), 'utf8'); }
	catch { return ''; }
};

test('T-326: page delegates refinement planning and fan-out but keeps transport and session coordination', () => {
	const fanout = read('./refinement-fanout.ts');
	const page = read('../../../routes/+page.svelte');

	assert.match(fanout, /export async function planRefinementCandidates/);
	assert.match(fanout, /export async function runRefinementFanout/);
	assert.match(page, /planRefinementCandidates\(/);
	assert.match(page, /runRefinementFanout\(/);
	assert.doesNotMatch(page, /function colorCatalogCandidateIds\(/);
	assert.doesNotMatch(page, /function runWithLimit</);

	assert.match(page, /async function renderWordTouchCandidate\(/);
	assert.match(page, /async function composeVariationCandidate\(/);
	assert.match(page, /async function interpretationVariationCandidate\(/);
	assert.match(page, /async function variationCandidateLabel\(/);
	assert.match(page, /async function renderColorCatalogCandidate\(/);
	assert.match(page, /async function allocateVariationSeeds\(/);

	const generateStart = page.indexOf('async function generateVariationCandidates');
	const showStart = page.indexOf('function showVariationCandidate', generateStart);
	const generate = page.slice(generateStart, showStart);
	assert.match(generate, /refinementSession\.beginGrid\(/);
	assert.match(generate, /window\.setTimeout\(/);
	assert.match(generate, /refinementSession\.setPlans\(/);
	assert.match(generate, /refinementSession\.commitCandidates\(/);
	assert.match(generate, /refinementSession\.finishGrid\(/);
});
