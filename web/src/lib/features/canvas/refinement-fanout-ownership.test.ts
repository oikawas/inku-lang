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

test('T-326: coordinator delegates refinement planning and fan-out but keeps transport and session coordination', () => {
	const fanout = read('./refinement-fanout.ts');
	const coordinator = read('./refinement-coordinator.svelte.ts');

	assert.match(fanout, /export async function planRefinementCandidates/);
	assert.match(fanout, /export async function runRefinementFanout/);
	assert.match(coordinator, /planRefinementCandidates\(/);
	assert.match(coordinator, /runRefinementFanout\(/);
	assert.doesNotMatch(coordinator, /function colorCatalogCandidateIds\(/);
	assert.doesNotMatch(coordinator, /function runWithLimit</);

	assert.match(coordinator, /async function renderWordTouchCandidate\(/);
	assert.match(coordinator, /async function composeVariationCandidate\(/);
	assert.match(coordinator, /async function interpretationVariationCandidate\(/);
	assert.match(coordinator, /async function variationCandidateLabel\(/);
	assert.match(coordinator, /async function renderColorCatalogCandidate\(/);
	assert.match(coordinator, /async function allocateVariationSeeds\(/);

	const generateStart = coordinator.indexOf('async function generateVariationCandidates');
	const showStart = coordinator.indexOf('function showVariationCandidate', generateStart);
	const generate = coordinator.slice(generateStart, showStart);
	assert.match(generate, /refinementSession\.beginGrid\(/);
	assert.match(generate, /window\.setTimeout\(/);
	assert.match(generate, /refinementSession\.setPlans\(/);
	assert.match(generate, /refinementSession\.commitCandidates\(/);
	assert.match(generate, /refinementSession\.finishGrid\(/);
});
