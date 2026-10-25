// The per-work Stage 1/2 prompt digests stopped being written with the Python
// Stage 1/2 (2026-09-14). Generation info no longer shows them as "not
// recorded"; the prompt tab shows the shared core's digest for each stage.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

test('generation info carries none of the three retired digests', () => {
	const info = read('./CanvasGenerationInfo.svelte');
	assert.doesNotMatch(info, /stage1_prompt_digest|stage1_prompt_base_digest|stage2_prompt_digest/);
	assert.doesNotMatch(info, /provenanceLabelStage[12]Prompt/);
});

test('the prompt tab shows each recorded stage its prompt digest', () => {
	const tabs = read('../../components/OutputTabsContent.svelte');
	assert.match(tabs, /\{#snippet promptDigest\(sent: SentSystemPrompt\)\}[\s\S]*?sent\.prompt_digest/);
	assert.equal((tabs.match(/\{@render promptDigest\(/g) ?? []).length, 3, 'shared stages, Stage 1 and Stage 2');
	assert.match(tabs, /\{@render promptDigest\(stage1System\)\}/);
	assert.match(tabs, /\{@render promptDigest\(stage2System\)\}/);
});
