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

function coordinatorFunction(coordinator: string, name: string): string {
	const start = coordinator.indexOf(`async function ${name}(`);
	assert.notEqual(start, -1, `${name} must remain a coordinator wrapper`);
	const next = coordinator.indexOf('\n\tasync function ', start + 1);
	return coordinator.slice(start, next === -1 ? coordinator.length : next);
}

test('T-331: coordinator delegates single redraw actions and keeps target coordination', () => {
	const action = read('./refinement-redraw.ts');
	const coordinator = read('./refinement-coordinator.svelte.ts');

	for (const name of ['runTouchRedraw', 'runLayoutRedraw', 'runReadingRedraw', 'projectRefinementRedrawResult']) {
		assert.match(action, new RegExp(`export (?:async )?function ${name}`));
		assert.match(coordinator, new RegExp(`${name}\\(`));
	}

	const touch = coordinatorFunction(coordinator, 'varyPerformance');
	const layout = coordinatorFunction(coordinator, 'varyComposition');
	const reading = coordinatorFunction(coordinator, 'varyInterpretation');
	assert.doesNotMatch(touch, /apiFetch\(['"]\/api\/render-svg/);
	assert.doesNotMatch(touch, /const usedSeeds = new Set/);
	assert.match(touch, /const contextVersion = targetIdentityVersion/);
	assert.match(touch, /isCurrentTarget: \(\) => contextVersion === targetIdentityVersion/);
	assert.match(touch, /if \(!redrawn\) return/);
	assert.doesNotMatch(layout + reading, /elapsedStage1Ms = r\.elapsed_stage1_ms/);

	for (const wrapper of [touch, layout, reading]) {
		assert.match(wrapper, /work\.confirmFallbackRefine\(/);
		assert.match(wrapper, /deps\.ensureVisibleLineageParentId\(/);
		assert.match(wrapper, /refinementSession\.beginSingle\(/);
		assert.match(wrapper, /refinementSession\.finishSingle\(/);
		assert.match(wrapper, /deps\.fitCanvas\(\)/);
	}
	assert.match(layout, /deps\.history\.fetchOffset\(/);
	assert.match(reading, /deps\.buildDdlDiffParts\(/);
});
