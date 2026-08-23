import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const page = readFileSync(new URL('../../../routes/+page.svelte', import.meta.url), 'utf8');
const owner = readFileSync(new URL('./state.svelte.ts', import.meta.url), 'utf8');
const work = readFileSync(new URL('../work/state.svelte.ts', import.meta.url), 'utf8');

test('T-801: the route constructs one BatchState and no longer owns its state machine', () => {
	assert.equal((page.match(/new BatchState(?:<[^>]+>)?\(/g) ?? []).length, 1);
	for (const staleOwner of [
		'let batchCurrent = $state',
		'let batchFailures = $state',
		'function refreshBatchResume',
		'function collectBatchRunWorks',
		'const paintBatchLine = async',
		'planRetryRound(',
	]) {
		assert.doesNotMatch(page, new RegExp(staleOwner.replace(/[.*+?^${}()|[\]\\]/g, '\\$&')));
	}
	assert.match(owner, /export class BatchState/);
	assert.match(owner, /private abortController: AbortController \| null/);
	assert.match(owner, /planRetryRound\(/);
});

test('T-807: BatchState receives narrow capabilities, not route controllers or a generic bag', () => {
	assert.doesNotMatch(owner, /HistoryBrowsingState|SettingsController|CanvasViewportState|Record<string, unknown>/);
	assert.match(work, /paintLine: \(text, paintOptions\) => paintOne\(text, paintOptions\)/);
	assert.match(work, /refreshAfterServerSave: \(\) => deps\.history\(\)\.refreshAfterServerSave\(\)/);
	assert.match(work, /refreshAfterRun: \(\) => deps\.history\(\)\.refreshAfterRun\(\)/);
});
