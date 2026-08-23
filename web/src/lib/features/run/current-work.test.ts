import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import type { LangPack } from '../../i18n/types.ts';
import { runCurrentWork } from './current-work.ts';

const strings = {
	stageSketching: 'sketching',
	stageInterpreting: 'interpreting',
	stageStructuring: () => 'structuring',
	stagePerforming: 'performing'
} as LangPack;

function paintStream(events: Array<Record<string, unknown>>): Response {
	return new Response(`${events.map((event) => JSON.stringify(event)).join('\n')}\n`, {
		status: 200,
		headers: { 'Content-Type': 'application/x-ndjson' }
	});
}

function doneEvent(overrides: Record<string, unknown> = {}): Record<string, unknown> {
	return {
		event: 'done',
		ddl: 'circle',
		thinking: null,
		svg: '<svg/>',
		score: {},
		elapsed_stage1_ms: 11,
		elapsed_stage2_ms: 12,
		elapsed_total_ms: 23,
		tokens_in_stage1: 2,
		tokens_out_stage1: 3,
		tokens_in_stage2: 4,
		tokens_out_stage2: 5,
		result_marker: 'same done payload',
		...overrides
	};
}

test('T-259: one current-work run owns the paint request and preserves caller overrides', async () => {
	const controller = new AbortController();
	const calls: Array<{ path: string; init?: RequestInit }> = [];
	const labels: string[] = [];
	let attachments = 0;

	const result = await runCurrentWork(
		'a red circle',
		{
			historyInput: 'original words',
			saveHistory: false,
			saveArtifacts: false,
			countGeneration: false,
			canvasAspectId: 'vertical',
			renderSeed: 17,
			compositionSeed: 19,
			variationAmplitude: 'small',
			variationSeed: 23,
			interpretationSeed: 'seed',
			seedText: 'seed text',
			sourceText: 'source words',
			displayLabel: 'line 2',
			batchLineNumber: 2,
			batchRunId: 'batch-1',
			historyVisibility: 'lineage_only',
			lineageParentNodeId: 'parent-1',
			derivationKind: 'variation',
			derivationMetadata: { source: 'test' },
			sketchMode: 'coarse',
			sketchText: 'observed prose',
			stage1Model: 'provider/one',
			stage2Model: 'provider/two',
			signal: controller.signal
		},
		{
			uiLang: 'en',
			strings,
			stage1Model: 'default/stage-1',
			stage2Model: 'default/stage-2',
			includeThinking: true,
			instructionLang: 'auto',
			canvasAspectId: 'square',
			ddlAutoRepairEnabled: true,
			sketchMode: 'fine',
			renderPayload: { render_wild: true }
		},
		{
			apiFetch: async (path, init) => {
				calls.push({ path, init });
				return paintStream([doneEvent()]);
			},
			describeApiError: () => 'request failed',
			setStage1UserPrompt: () => undefined,
			setStageLabel: (label) => labels.push(label),
			setActiveRunTokens: () => undefined,
			loadNearbyHistory: async () => undefined,
			attachSavedLineage: () => { attachments += 1; },
			updateGenerationCount: () => undefined
		}
	);

	assert.equal(calls[0]?.path, '/api/paint/stream');
	assert.equal(calls[0]?.init?.signal, controller.signal);
	const body = JSON.parse(String(calls[0]?.init?.body)) as Record<string, unknown>;
	assert.deepEqual(body, {
		description: 'a red circle',
		sketch: true,
		sketch_grain: 'coarse',
		sketch_text: 'observed prose',
		stage1_model: 'provider/one',
		stage2_model: 'provider/two',
		include_thinking: true,
		instruction_lang: 'auto',
		ui_lang: 'en',
		canvas_aspect: 'vertical',
		render_seed: 17,
		composition_seed: 19,
		variation_amplitude: 'small',
		variation_seed: 23,
		interpretation_seed: 'seed',
		seed_text: 'seed text',
		auto_repair: true,
		save_history: false,
		save_artifacts: false,
		count_generation: false,
		history_input: 'original words',
		history_source_text: 'source words',
		history_display_label: 'line 2',
		batch_line_number: 2,
		batch_run_id: 'batch-1',
		history_visibility: 'lineage_only',
		lineage_parent_node_id: 'parent-1',
		derivation_kind: 'variation',
		derivation_metadata: { source: 'test' },
		render_wild: true
	});
	assert.equal(result.ddl, 'circle');
	assert.equal((result as unknown as { result_marker: string }).result_marker, 'same done payload');
	assert.deepEqual(labels, ['sketching']);
	assert.equal(attachments, 0);
});

test('T-260/T-261: stream progress and saved-work effects cross named capabilities', async () => {
	const labels: string[] = [];
	const tokenPairs: Array<[number | null, number | null]> = [];
	const nearby: Array<string | null | undefined> = [];
	const prompts: string[] = [];
	const stage1Events: unknown[] = [];
	let attached = 0;
	let generationCount: number | null = null;

	await runCurrentWork(
		'blue square',
		{ onStage1: (event) => stage1Events.push(event) },
		{
			uiLang: 'ja',
			strings,
			stage1Model: 'default/stage-1',
			stage2Model: 'default/stage-2',
			includeThinking: false,
			instructionLang: 'ja',
			canvasAspectId: 'square',
			ddlAutoRepairEnabled: false,
			sketchMode: 'fine',
			renderPayload: {}
		},
		{
			apiFetch: async () => paintStream([
				{
					event: 'stage1',
					ddl: 'square',
					thinking: null,
					stage1_model: 'default/stage-1',
					stage2_model: 'default/stage-2',
					tokens_in: 7,
					tokens_out: 8,
					elapsed_ms: 9,
					interpret_fallback_used: false
				},
				{ event: 'score', instruction_count: 1, stage2_model: 'default/stage-2', tokens_in: 4, tokens_out: 5, elapsed_ms: 6 },
				doneEvent({ history_id: 'history-1', lineage_node_id: 'lineage-1', user_generation_count: 31 })
			]),
			describeApiError: () => 'request failed',
			setStage1UserPrompt: (prompt) => prompts.push(prompt),
			setStageLabel: (label) => labels.push(label),
			setActiveRunTokens: (tokensIn, tokensOut) => tokenPairs.push([tokensIn, tokensOut]),
			loadNearbyHistory: async (historyId) => { nearby.push(historyId); },
			attachSavedLineage: () => { attached += 1; },
			updateGenerationCount: (count) => { generationCount = count; }
		}
	);

	assert.deepEqual(prompts, ['blue square']);
	assert.deepEqual(labels, ['sketching', 'structuring', 'performing']);
	assert.deepEqual(tokenPairs, [[null, null], [7, 8], [null, null]]);
	assert.equal(stage1Events.length, 1);
	assert.deepEqual(nearby, ['history-1']);
	assert.equal(attached, 1);
	assert.equal(generationCount, 31);
});

test('T-260: an HTTP failure uses the page-provided error wording', async () => {
	await assert.rejects(
		runCurrentWork(
			'circle',
			{},
			{
				uiLang: 'en',
				strings,
				stage1Model: 'default/stage-1',
				stage2Model: 'default/stage-2',
				includeThinking: false,
				instructionLang: 'en',
				canvasAspectId: 'square',
				ddlAutoRepairEnabled: false,
				sketchMode: 'off',
				renderPayload: {}
			},
			{
				apiFetch: async () => new Response(JSON.stringify({ detail: 'provider down' }), { status: 503 }),
				describeApiError: (detail, status) => `${status}: ${String(detail)}`,
				setStage1UserPrompt: () => undefined,
				setStageLabel: () => undefined,
				setActiveRunTokens: () => undefined,
				loadNearbyHistory: async () => undefined,
				attachSavedLineage: () => undefined,
				updateGenerationCount: () => undefined
			}
		),
		/503: provider down/
	);
});

test('T-263/T-264: the operation stays stateless and Work keeps outer-run ownership', () => {
	const owner = readFileSync(new URL('./current-work.ts', import.meta.url), 'utf8');
	const page = readFileSync(new URL('../../../routes/+page.svelte', import.meta.url), 'utf8');
	const work = readFileSync(new URL('../work/state.svelte.ts', import.meta.url), 'utf8');

	assert.equal((owner.match(/\/api\/paint\/stream/g) ?? []).length, 1);
	assert.doesNotMatch(page, /\/api\/paint\/stream/);
	assert.doesNotMatch(owner, /\$state|new AbortController|currentUser|lineageDetached/);
	assert.match(work, /new AbortController/);
	assert.match(work, /return runCurrentWork\(/);
	assert.match(owner, /type CurrentWorkCapabilities = \{/);
	assert.match(owner, /setActiveRunTokens:/);
	assert.match(owner, /loadNearbyHistory:/);
	assert.match(owner, /attachSavedLineage:/);
	assert.match(owner, /updateGenerationCount:/);
});
