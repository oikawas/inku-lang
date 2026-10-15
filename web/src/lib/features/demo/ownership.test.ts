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
	const paintInstruction = work.match(/paintInstruction\s*:\s*\(\s*prompt\s*,\s*paintOptions\s*\)\s*=>\s*\{([\s\S]*?)\}\s*,/);
	assert.ok(paintInstruction, 'DemoState receives a scoped paintInstruction callback');
	const paintInstructionBody = paintInstruction[1].replace(/\s+/g, '');
	assert.match(paintInstructionBody, /constmodel=qualifiedModelId\(deps\.models\.stage1Provider\(\),deps\.models\.stage1Model\(\)\);/);
	assert.match(paintInstructionBody, /returnpaintOne\(prompt,\{\.\.\.paintOptions,stage1Model:model,stage2Model:model\}\);/);
	assert.match(work, /refreshAfterServerSave: \(\) => deps\.history\(\)\.refreshAfterServerSave\(\)/);
	assert.match(work, /refreshAfterRun: \(\) => deps\.history\(\)\.refreshAfterRun\(\)/);
});
