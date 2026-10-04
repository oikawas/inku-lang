import assert from 'node:assert/strict';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

import type { BatchFailureReport } from '../batch/failure-report.svelte.ts';
import type { WorkStateDeps } from './state.svelte.ts';
import type { PipelineView } from '../pipeline/api.ts';

const libRoot = new URL('../../', import.meta.url);
registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier.startsWith('$lib/')) {
			return nextResolve(new URL(`${specifier.slice(5)}.ts`, libRoot).href, context);
		}
		return nextResolve(specifier, context);
	}
});
const identity = <T>(value: T): T => value;
const stateShim = Object.assign(identity, { raw: identity });
const derivedShim = Object.assign(identity, { by: <T>(read: () => T): T => read() });
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = stateShim;
runeHost.$derived = derivedShim;

const { BatchState } = await import('../batch/state.svelte.ts');
const { batchSettings } = await import('../batch/settings.svelte.ts');
const { createWorkState } = await import('./state.svelte.ts');
const { pipelineAttentionReason } = await import('../pipeline/attention.ts');

function failedView(description: string): PipelineView {
	return {
		execution_id: `execution-${description}`, variation_id: `variation-${description}`,
		authority: { revision: '0', origin: 'stage1_generated', authority: 'description_authoritative' },
		description, document: null, delivery: null, rendered: null, result: null, busy: false,
		phase: { tag: 'failed', reason: 'stage1_failed' },
		provider_failure: { failure: 'schema_violation', stage: 'stage1', attempt: 4 }
	};
}

function failureResponse(description: string): Response {
	return new Response(JSON.stringify({ detail: {
		code: 'pipeline_author_action_required', current_view: failedView(description)
	} }), { status: 409, headers: { 'Content-Type': 'application/json' } });
}

test('a batch drops the old single-work failure and retains its own line failures', async () => {
	let work: ReturnType<typeof createWorkState>;
	const paints: string[] = [];
	const reports: Array<BatchFailureReport | null> = [];
	const apiFetch: WorkStateDeps['apiFetch'] = async (path, init) => {
		assert.equal(path, '/api/paint/stream');
		const body = JSON.parse(String(init?.body)) as { description: string };
		paints.push(body.description);
		if (body.description !== 'single failure') {
			assert.equal(pipelineAttentionReason(work.pipelineView?.phase), null);
		}
		if (body.description !== 'drawn line') return failureResponse(body.description);
		return new Response(`${JSON.stringify({
			event: 'done', ddl: 'drawn line', thinking: null, svg: '<svg/>', score: { instructions: [] },
			elapsed_stage1_ms: 1, elapsed_stage2_ms: 0, elapsed_total_ms: 1,
			tokens_in_stage1: 2, tokens_out_stage1: 3,
			tokens_in_stage2: null, tokens_out_stage2: null
		})}\n`, { headers: { 'Content-Type': 'application/x-ndjson' } });
	};
	const batch = new BatchState({
		apiFetch, signedIn: () => true, paintable: (text) => text.trim().length > 0,
		setFailureReport: (report) => reports.push(report), createRunId: () => 'batch-test'
	});
	batch.input = 'drawn line\nfailed line';
	batchSettings.maxRetries = 0;
	work = createWorkState({
		apiFetch, batch,
		describeApiError: () => 'schema_violation: 4 attempts',
		session: { updateGenerationCount: () => {} },
		demo: { latestResult: null, updateLiveTime: () => {} },
		refinementSession: { gridBusy: false },
		canvasViewport: { fit: () => {} },
		history: () => ({
			clearSelection: () => {}, refreshAfterServerSave: async () => {}, refreshAfterRun: async () => {}
		}),
		models: {
			stage1Provider: () => 'local-mlx', stage1Model: () => 'mlx-community/gemma-4-12B-it-4bit',
			stage2Provider: () => 'local-mlx', stage2Model: () => 'mlx-community/gemma-4-12B-it-4bit',
			includeThinking: () => false, available: () => []
		},
		canvasAspectId: () => 'square', resetTargetScopedState: () => {},
		ensureVisibleLineageParentId: async () => null, showCanvas: () => {},
		requestConfirmation: () => {}, displayLatestBatchRender: () => {}, pushHistory: async () => null
	} as unknown as WorkStateDeps);

	await work.pipelineCompatibilityError(failureResponse('old single failure'));
	assert.equal(pipelineAttentionReason(work.pipelineView?.phase), 'stage1_failed');
	work.inputMode = 'batch';
	await work.submitBatch({});
	assert.equal(work.pipelineView, null);
	assert.equal(batch.success, 1);
	assert.deepEqual(reports.at(-1), {
		success: 1, total: 2,
		failures: [{ line: 2, input: 'failed line', message: 'schema_violation: 4 attempts' }]
	});
	assert.deepEqual(paints, ['drawn line', 'failed line']);

	work.inputMode = 'single';
	await assert.rejects(work.paintOne('single failure'), /schema_violation: 4 attempts/);
	assert.equal(work.pipelineView?.description, 'single failure');
	assert.equal(pipelineAttentionReason(work.pipelineView?.phase), 'stage1_failed');
});

test('a new drawing uses the changed model and clears the preceding failure without reloading', async () => {
	let model = 'chatgpt:luna';
	let work: ReturnType<typeof createWorkState>;
	const models: string[] = [];
	const apiFetch: WorkStateDeps['apiFetch'] = async (path, init) => {
		assert.equal(path, '/api/paint/stream');
		const body = JSON.parse(String(init?.body)) as { description: string; stage1_model: string; stage2_model: string };
		models.push(body.stage1_model);
		assert.equal(body.stage2_model, model);
		if (models.length === 1) return failureResponse(body.description);
		assert.equal(pipelineAttentionReason(work.pipelineView?.phase), null);
		return new Response(`${JSON.stringify({
			event: 'done', ddl: 'red circle', thinking: null, svg: '<svg><circle/></svg>', score: { instructions: [] },
			elapsed_stage1_ms: 1, elapsed_stage2_ms: 0, elapsed_total_ms: 1,
			tokens_in_stage1: 2, tokens_out_stage1: 3, tokens_in_stage2: null, tokens_out_stage2: null
		})}\n`, { headers: { 'Content-Type': 'application/x-ndjson' } });
	};
	work = createWorkState({
		apiFetch, batch: {}, describeApiError: () => 'the previous model failed',
		session: { updateGenerationCount: () => {} }, demo: { latestResult: null }, refinementSession: { gridBusy: false },
		canvasViewport: { fit: () => {} }, history: () => ({}),
		models: { stage1Provider: () => null, stage2Provider: () => null, stage1Model: () => model,
			stage2Model: () => model, includeThinking: () => false, available: () => [] },
		canvasAspectId: () => 'square', resetTargetScopedState: () => {}, showCanvas: () => {},
	} as unknown as WorkStateDeps);
	await assert.rejects(work.paintOne('red circle', { saveHistory: false }), /previous model failed/);
	assert.equal(pipelineAttentionReason(work.pipelineView?.phase), 'stage1_failed');
	model = 'openai:other';
	assert.equal((await work.paintOne('red circle', { saveHistory: false })).svg, '<svg><circle/></svg>');
	assert.equal(work.pipelineView, null);
	assert.deepEqual(models, ['chatgpt:luna', 'openai:other']);
});
