// Run with: node --import ./scripts/ts-extensionless-resolve.mjs --test src/lib/components/variation-lanes-stagger.test.ts
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const LANES = read('./VariationLanes.svelte');
const COORDINATOR = read('../features/canvas/refinement-coordinator.svelte.ts');

test('each lane draws its offset when it turns to running, not when the row mounts', () => {
	// The AI's theses are sent after the row is shown and before any lane runs,
	// so an offset drawn at mount has run out by the time the lanes start.
	assert.match(COORDINATOR, /beginGrid\(\{ includesReading: true, taskLabel: t\(\)\.workActionComposition, count \}\)[\s\S]*?await proposeTheses\(/);
	assert.match(LANES, /if \(state !== 'running' \|\| scheduled\.has\(index\)\) return;\s*scheduled\.set\(index, window\.setTimeout\(/);
	assert.match(LANES, /Math\.random\(\) \* STAGGER_MS/);
	assert.doesNotMatch(LANES, /untrack\(\(\) => states\.length\)/);
	// A lane shows its mascot only after its own offset, never by default.
	assert.match(LANES, /\{:else if started\[index\]\}/);
});

test('a lane back to waiting forgets its offset, so a new run in the same row is staggered again', () => {
	assert.match(LANES, /if \(state === 'waiting' && scheduled\.has\(index\)\) \{\s*window\.clearTimeout\(scheduled\.get\(index\)\);\s*scheduled\.delete\(index\);/);
});
