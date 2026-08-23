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

function pageFunction(page: string, name: string): string {
	const start = page.indexOf(`async function ${name}(`);
	assert.notEqual(start, -1, `${name} must remain a page coordination wrapper`);
	const next = page.indexOf('\n\tasync function ', start + 1);
	return page.slice(start, next === -1 ? page.length : next);
}

test('T-331: page delegates single redraw actions but keeps route and view coordination', () => {
	const action = read('./refinement-redraw.ts');
	const page = read('../../../routes/+page.svelte');

	for (const name of ['runTouchRedraw', 'runLayoutRedraw', 'runReadingRedraw', 'projectRefinementRedrawResult']) {
		assert.match(action, new RegExp(`export (?:async )?function ${name}`));
		assert.match(page, new RegExp(`${name}\\(`));
	}

	const touch = pageFunction(page, 'varyPerformance');
	const layout = pageFunction(page, 'varyComposition');
	const reading = pageFunction(page, 'varyInterpretation');
	assert.doesNotMatch(touch, /apiFetch\(['"]\/api\/render-svg/);
	assert.doesNotMatch(touch, /const usedSeeds = new Set/);
	assert.match(touch, /const contextVersion = targetContextVersion/);
	assert.match(touch, /isCurrentTarget: \(\) => contextVersion === targetContextVersion/);
	assert.match(touch, /if \(!redrawn\) return/);
	assert.doesNotMatch(layout + reading, /elapsedStage1Ms = r\.elapsed_stage1_ms/);

	for (const wrapper of [touch, layout, reading]) {
		assert.match(wrapper, /confirmFallbackRefine\(/);
		assert.match(wrapper, /ensureVisibleLineageParentId\(/);
		assert.match(wrapper, /refinementSession\.beginSingle\(/);
		assert.match(wrapper, /refinementSession\.finishSingle\(/);
		assert.match(wrapper, /canvasViewport\.fit\(\)/);
	}
	assert.match(layout, /history\.fetchOffset\(/);
	assert.match(reading, /buildDdlDiffParts\(/);
});
