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

test('T-303/T-304: page and panel use one route-instance Canvas viewport owner', () => {
	const owner = read('./viewport-state.svelte.ts');
	const page = read('../../../routes/+page.svelte');
	const panel = read('../../components/CanvasPanel.svelte');
	const work = read('../work/state.svelte.ts');
	const refinement = read('./refinement-coordinator.svelte.ts');

	assert.match(owner, /export class CanvasViewportState/);
	assert.match(page, /new CanvasViewportState\(\)/);
	// Every fit goes through the one owner: the page and the work owner call it
	// directly, and the refinement coordinator through the capability the page
	// wires to it. Checked per owner rather than as one total, which fell with
	// the consolidation of the result paths (2026-09-13) without any fit
	// leaving the owner -- and which never counted the coordinator's calls.
	const count = (source: string, pattern: RegExp) => (source.match(pattern) ?? []).length;
	assert.ok(count(page, /canvasViewport\.fit\(\)/g) >= 1);
	assert.ok(count(work, /canvasViewport\.fit\(\)/g) >= 1);
	assert.match(page, /fitCanvas: \(\) => canvasViewport\.fit\(\)/);
	assert.ok(count(refinement, /deps\.fitCanvas\(\)/g) >= 1);
	assert.doesNotMatch(page, /let zoom\s*=\s*\$state/);
	assert.doesNotMatch(page, /function fitCanvasZoom/);
	assert.doesNotMatch(page, /\bresetZoom\b/);

	assert.match(panel, /viewport:\s*CanvasViewport/);
	assert.match(panel, /viewport\.updateFitZoom/);
	assert.match(panel, /viewport\.startDrag/);
	assert.doesNotMatch(panel, /onSetZoom:/);
	assert.doesNotMatch(panel, /onFitZoomChange:/);
});
