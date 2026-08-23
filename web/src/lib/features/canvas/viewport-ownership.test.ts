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
	const fitCalls = [page, work, refinement]
		.reduce((count, source) => count + (source.match(/(?:canvasViewport|deps\.fitCanvas\(\))\.fit?\(?/g) ?? []).length, 0);
	assert.ok(fitCalls >= 10);
	assert.doesNotMatch(page, /let zoom\s*=\s*\$state/);
	assert.doesNotMatch(page, /function fitCanvasZoom/);
	assert.doesNotMatch(page, /\bresetZoom\b/);

	assert.match(panel, /viewport:\s*CanvasViewport/);
	assert.match(panel, /viewport\.updateFitZoom/);
	assert.match(panel, /viewport\.startDrag/);
	assert.doesNotMatch(panel, /onSetZoom:/);
	assert.doesNotMatch(panel, /onFitZoomChange:/);
});
