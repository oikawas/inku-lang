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

test('T-1001/T-1002: CanvasPanel delegates the current-artwork workspace once', () => {
	const panel = read('../../components/CanvasPanel.svelte');
	const artwork = read('./CanvasArtworkWorkspace.svelte');
	const types = read('./view-types.ts');

	assert.match(panel, /import CanvasArtworkWorkspace from '\$lib\/features\/canvas\/CanvasArtworkWorkspace\.svelte'/);
	assert.equal((panel.match(/<CanvasArtworkWorkspace/g) ?? []).length, 1);
	assert.match(artwork, /class="canvas-content"/);
	assert.match(artwork, /class="canvas-corner-controls canvas-corner-left"/);
	assert.match(artwork, /class="canvas-corner-controls canvas-corner-right"/);
	assert.match(artwork, /class="zoom-controls"/);
	assert.match(panel, /The drawing goes on the canvas as an image/);
	assert.match(artwork, /<img class="canvas-art" src=\{artworkUrl\}/);
	assert.doesNotMatch(panel, /class="canvas-corner-controls|class="zoom-controls/);
});

test('T-1002/T-1005: artwork view has a typed capability-local boundary and no owner state', () => {
	const artwork = read('./CanvasArtworkWorkspace.svelte');
	const types = read('./view-types.ts');

	assert.match(artwork, /type Props = \{/);
	assert.match(artwork, /viewport: CanvasViewport/);
	assert.match(artwork, /result: PaintResult \| null/);
	assert.match(artwork, /import type \{ PaintResult \} from '\$lib\/features\/run\/current-work'/);
	assert.match(artwork, /import type \{ SvgProfile \} from '\$lib\/features\/export\/download'/);
	assert.match(types, /export type CanvasStatusHistoryItem = Partial<HistoryItem>/);
	assert.match(types, /from '\$lib\/historyManagerState\.svelte'/);
	assert.doesNotMatch(artwork, /\$state\(|modelInspection|refinementSession|LineagePanel|CanvasGenerationInfo|CanvasPresentationOverlay|apiFetch|createContext|setContext|getContext/);
	assert.doesNotMatch(artwork + types, /\bany\b/);
});
