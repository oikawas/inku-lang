import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const page = readFileSync(new URL('../../../routes/+page.svelte', import.meta.url), 'utf8');
const owner = readFileSync(new URL('./state.svelte.ts', import.meta.url), 'utf8');
const work = readFileSync(new URL('../work/state.svelte.ts', import.meta.url), 'utf8');

test('T-901: the route constructs one DemoState and no longer owns its state machine', () => {
	assert.equal((page.match(/new DemoState(?:<[^>]+>)?\(/g) ?? []).length, 1);
	for (const staleOwner of [
		'let demoGeneratedPrompt = $state',
		'let demoSettings = $state',
		'let demoRunId = 0',
		'function normalizeDemoSettings',
		'async function generateDemoInstruction',
		'async function runDemoLoop',
	]) {
		assert.doesNotMatch(page, new RegExp(staleOwner.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
	}
	assert.doesNotMatch(page, /apiFetch\('\/api\/history'/);
	assert.match(owner, /export class DemoState/);
});

test('T-905/T-907: DemoState uses narrow capabilities and identity, without transport cancellation', () => {
	assert.doesNotMatch(owner, /HistoryBrowsingState|SettingsController|CanvasViewportState|Record<string, unknown>/);
	assert.doesNotMatch(owner, /AbortController|AbortSignal/);
	assert.match(owner, /private runIdentity = 0/);
	assert.match(work, /paintInstruction: \(prompt, paintOptions\) => paintOne\(prompt, paintOptions\)/);
	assert.match(work, /refreshAfterServerSave: \(\) => deps\.history\(\)\.refreshAfterServerSave\(\)/);
	assert.match(work, /refreshAfterRun: \(\) => deps\.history\(\)\.refreshAfterRun\(\)/);
});
