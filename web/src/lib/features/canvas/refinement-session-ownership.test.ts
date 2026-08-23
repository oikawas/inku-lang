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
	const actions = read('./refinement-actions.ts');
	const coordinator = read('./refinement-coordinator.svelte.ts');
	const view = read('./CanvasRefinementWorkspace.svelte');
	const page = read('../../../routes/+page.svelte');
	const panel = read('../../components/CanvasPanel.svelte');

	assert.match(owner, /export class RefinementSessionState/);
	assert.match(owner, /export type VariationCandidate/);
	assert.match(page, /new RefinementSessionState\(/);
	assert.doesNotMatch(page, /let variationGridBusy\s*=\s*\$state/);
	assert.doesNotMatch(page, /let variationCandidates\s*=\s*\$state/);
	assert.doesNotMatch(page, /variationGridAbortController/);
	assert.match(coordinator, /async function generateVariationCandidates/);
	assert.match(coordinator, /async function saveSelectedVariationCandidates/);
	assert.match(actions, /export function projectRefinementCandidate/);
	assert.match(actions, /export async function saveRefinementCandidates/);
	assert.match(coordinator, /projectRefinementCandidate\(candidate\)/);
	assert.match(coordinator, /saveRefinementCandidates\(/);
	const showStart = coordinator.indexOf('function showVariationCandidate');
	const saveStart = coordinator.indexOf('async function saveSelectedVariationCandidates');
	const returnStart = coordinator.indexOf('\n\treturn {', saveStart);
	assert.ok(showStart >= 0 && saveStart > showStart && returnStart > saveStart);
	assert.doesNotMatch(coordinator.slice(showStart, saveStart), /candidate\.result\.(?:source_ddl|ddl|thinking)/);
	assert.doesNotMatch(coordinator.slice(saveStart, returnStart), /pushHistory\(\{/);

	assert.match(panel, /refinementSession:\s*RefinementSession/);
	assert.match(panel, /<CanvasRefinementWorkspace[\s\S]*\{refinementSession\}/);
	assert.match(view, /refinementSession:\s*RefinementSession/);
	assert.doesNotMatch(view, /\$state\(/);
	assert.doesNotMatch(panel, /type VariationCandidate\s*=/);
	assert.doesNotMatch(panel, /variationGridBusy:/);
	assert.doesNotMatch(panel, /onAbortVariationCandidates:/);
	assert.doesNotMatch(panel, /onToggleVariationCandidate:/);
});
