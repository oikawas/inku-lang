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

test('T-312/T-313: page and panel share one typed refinement session owner', () => {
	const owner = read('./refinement-session.svelte.ts');
	const page = read('../../../routes/+page.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(owner, /export class RefinementSessionState/);
	assert.match(owner, /export type VariationCandidate/);
	assert.match(page, /new RefinementSessionState\(/);
	assert.doesNotMatch(page, /let variationGridBusy\s*=\s*\$state/);
	assert.doesNotMatch(page, /let variationCandidates\s*=\s*\$state/);
	assert.doesNotMatch(page, /variationGridAbortController/);
	assert.match(page, /async function generateVariationCandidates/);
	assert.match(page, /async function saveSelectedVariationCandidates/);

	assert.match(panel, /refinementSession:\s*RefinementSession/);
	assert.doesNotMatch(panel, /type VariationCandidate\s*=/);
	assert.doesNotMatch(panel, /variationGridBusy:/);
	assert.doesNotMatch(panel, /onAbortVariationCandidates:/);
	assert.doesNotMatch(panel, /onToggleVariationCandidate:/);
});
