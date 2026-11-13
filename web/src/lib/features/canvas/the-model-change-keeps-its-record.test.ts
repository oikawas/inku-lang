// Run with: npm run test:unit  (node:test, no test dependency)
// Step 1d (2026-11-13, the author chose "change it"): the model change draws
// each option as a fork of the work's pipeline, in the way the work itself was
// drawn, and saves the chosen run as the child, so the child keeps its own
// composition record. The input panel's route and switches do not enter.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const coordinator = readFileSync(new URL('./refinement-coordinator.svelte.ts', import.meta.url), 'utf8');
const modelCandidate = coordinator.slice(coordinator.indexOf('async function renderModelCandidate'), coordinator.indexOf('/** The work in every other catalog'));

test('a model option is a fork drawn the way the work was drawn, saved as its run', () => {
	assert.match(modelCandidate, /pipeline\.fromDescription\(/);
	assert.doesNotMatch(modelCandidate, /paintOne\(/);
	assert.match(modelCandidate, /const route = recorded\?\.route \?\? drawRouteOf\(shown\)/);
	assert.match(modelCandidate, /const composition = recorded\?\.composition \?\? compositionModeOf\(shown\)/);
	assert.match(modelCandidate, /save_history: false/);
	assert.match(modelCandidate, /derivation_kind: 'model_comparison'/);
	assert.match(modelCandidate, /executionId: view\.execution_id/);
	// The save names the option's own kind, not the composition form's.
	assert.match(coordinator, /derivation_kind: candidate\.result\.derivation_kind, derivation_metadata/);
});
