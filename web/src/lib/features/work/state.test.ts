import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

import type { BatchFailureReport } from '../batch/failure-report.svelte.ts';
import type { WorkStateDeps } from './state.svelte.ts';
import type { PipelineView } from '../pipeline/api.ts';

const libRoot = new URL('../../', import.meta.url);
registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier.startsWith('$lib/')) {
			// A directory module ($lib/plugins/system/canvas-aspect) resolves to its index.
			const file = new URL(`${specifier.slice(5)}.ts`, libRoot);
			const target = existsSync(file) ? file : new URL(`${specifier.slice(5)}/index.ts`, libRoot);
			return nextResolve(target.href, context);
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

function imageWork(apiFetch: WorkStateDeps['apiFetch'], overrides: Partial<WorkStateDeps> = {}) {
	return createWorkState({
		apiFetch, batch: { resuming: false }, demo: { running: false, updateLiveTime: () => {} },
		refinementSession: { gridBusy: false }, session: {},
		describeApiError: (detail: unknown) => (detail as { code: string }).code,
		history: () => ({ clearSelection: () => {} }),
		canvasViewport: { fit: () => {} }, canvasAspectId: () => 'square',
		resetTargetScopedState: () => {}, showCanvas: () => {},
		models: { stage1Provider: () => 'openai', stage1Model: () => 'text-only',
			stage2Provider: () => 'openai', stage2Model: () => 'text-only',
			visionProvider: () => 'chatgpt', visionModel: () => 'vision',
			includeThinking: () => false, available: () => [] },
		...overrides,
	} as unknown as WorkStateDeps);
}

const uploaded = (id: string) => ({ image_id: id, thumbnail: 'data:image/jpeg;base64,preview',
	original_width: 200, original_height: 100, width: 200, height: 100, nearest_format_id: 'hd_monitor' });

const beforeReview = '画面比2:1。\n背景を黄で埋める。';
const afterReview = '画面比2:1。\n背景を赤で埋める。';
function recordedImage(ddl = afterReview) {
	return { id: 'image-work', input: '', source_text: '', ddl, at: 1, svg: '<svg/>', score: { instructions: [] },
		lineage_node_id: 'image-node', image_provenance: 'source note', image_ddl: { before_review: beforeReview } };
}
function imageResult(ddl = afterReview) {
	return { ...recordedImage(ddl), history_id: 'image-work', elapsed_stage1_ms: 0, elapsed_stage2_ms: 0,
		elapsed_total_ms: 1, tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: null, tokens_out_stage2: null };
}

test('before-review instructions belong only to the displayed completed image work', () => {
	const work = imageWork(async () => { throw new Error('no request expected'); });
	work.inputMode = 'image';
	assert.equal(work.imageBeforeReviewDdl, null);
	work.result = imageResult();
	assert.equal(work.imageBeforeReviewDdl, beforeReview);
	work.displayedHistoryItem = { ...recordedImage(), image_ddl: { rounds: [] } };
	assert.equal(work.imageBeforeReviewDdl, null);
	work.displayedHistoryItem = { ...recordedImage(), image_ddl: null };
	assert.equal(work.imageBeforeReviewDdl, null);
	work.displayedHistoryItem = recordedImage();
	assert.equal(work.imageBeforeReviewDdl, beforeReview);
	work.inputMode = 'single';
	assert.equal(work.imageBeforeReviewDdl, null);
});

for (const unchanged of [false, true]) {
	test(`before-review redraw forks the original through DDL editing (${unchanged ? 'same' : 'different'} final DDL)`, async () => {
		const requests: Array<Record<string, unknown>> = [];
		const original = recordedImage(unchanged ? beforeReview : afterReview);
		const work = imageWork(async (path, init) => {
			assert.equal(path, '/api/pipeline/history/image-work/fork');
			requests.push(JSON.parse(String(init?.body)));
			return Response.json({ detail: 'captured before provider' }, { status: 400 });
		}, { ensureVisibleLineageParentId: async () => 'image-node' });
		work.inputMode = 'image'; work.input = '';
		work.lineageDetached = true;
		work.result = imageResult(original.ddl);
		work.displayedHistoryItem = original;
		work.ddl = original.ddl; work.ddlGeneratedBaseline = original.ddl;
		await work.selectHistoryAuthority('image-work', 'image-variation');
		await work.replayImageBeforeReview();
		assert.equal(requests.length, 1);
		assert.equal(requests[0].kind, 'direct_ddl');
		assert.equal(requests[0].text, beforeReview);
		const options = requests[0].options as Record<string, unknown>;
		assert.equal(options.lineage_parent_node_id, 'image-node');
		assert.equal(options.derivation_kind, 'ddl_edit');
		assert.equal(options.canvas_fit, 'contain');
		assert.equal(original.ddl, unchanged ? beforeReview : afterReview);
		assert.equal(work.ddlGeneratedBaseline, original.ddl);
		assert.equal(work.input, '');
	});
}

test('before-review redraw confirms draft replacement and ignores a confirmation for another work', async () => {
	let confirmation: Parameters<WorkStateDeps['requestConfirmation']>[0] | null = null;
	const work = imageWork(async () => { throw new Error('no request before confirmation'); }, {
		requestConfirmation: (value) => { confirmation = value; },
	});
	work.inputMode = 'image'; work.result = imageResult(); work.displayedHistoryItem = recordedImage();
	work.ddlGeneratedBaseline = afterReview; work.ddl = 'unfinished author edit';
	await work.replayImageBeforeReview();
	assert.ok(confirmation);
	assert.equal(work.ddl, 'unfinished author edit');
	work.displayedHistoryItem = { ...recordedImage(), id: 'another-work' };
	confirmation.run();
	assert.equal(work.ddl, 'unfinished author edit');
	work.reloading = true;
	work.ddl = afterReview;
	await work.replayImageBeforeReview();
	assert.equal(work.ddl, afterReview);
});

test('before-review action leaves ordinary unedited replay on its saved-Score path', async () => {
	const requests: string[] = [];
	const work = imageWork(async (path) => {
		requests.push(path);
		return Response.json({ detail: 'captured before rendering' }, { status: 400 });
	}, { ensureVisibleLineageParentId: async () => 'image-node' });
	work.inputMode = 'image'; work.result = imageResult(); work.displayedHistoryItem = recordedImage();
	work.ddl = afterReview; work.ddlGeneratedBaseline = afterReview;
	await work.replay();
	assert.deepEqual(requests, ['/api/render-canvas-fit']);
});

test('image authoring keeps provenance out of description and reuploads consumed images for a second draw', async () => {
	const file = new File(['browser memory only'], 'source.tiff', { type: 'image/tiff' });
	let uploads = 0;
	const starts: Array<Record<string, unknown>> = [];
	const work = imageWork(async (path, init) => {
		if (path === '/api/pipeline/images') {
			assert.equal(init?.body, file);
			assert.deepEqual(init?.headers, { 'Content-Type': 'application/octet-stream' });
			return Response.json(uploaded(`image-${++uploads}`));
		}
		assert.equal(path, '/api/pipeline/variations');
		const body = JSON.parse(String(init?.body));
		starts.push(body);
		return Response.json({ ...failedView('must not become a description'),
			phase: { tag: 'ready' }, image_provenance: body.text, image_ddl: { original_width: 200 } });
	});
	work.inputMode = 'image';
	work.imageProvenance = '# Source and private notes';
	work.sketchMode = 'on';
	await work.selectImage(file);
	await work.submitImage();
	await work.submitImage();
	assert.equal(uploads, 2);
	assert.deepEqual(starts.map((body) => body.image_id), ['image-1', 'image-2']);
	for (const body of starts) {
		assert.equal(body.kind, 'image');
		assert.equal(body.text, '# Source and private notes');
		assert.equal(body.canvas_format_id, 'image');
		const options = body.options as Record<string, unknown>;
		assert.equal(options.stage1_model, 'chatgpt:vision');
		assert.equal(options.stage2_model, 'chatgpt:vision');
		assert.equal(options.sketch, 'off');
		assert.equal(options.sketch_text, undefined);
		assert.equal(options.wild, false);
		assert.equal(options.canvas_fit, 'contain');
		assert.equal(options.instruction_lang, 'ja');
	}
	assert.equal(work.input, '');
	assert.equal(work.currentInstructionText, '');
	assert.equal(work.imageProvenance, '# Source and private notes');
	work.clearImage();
	assert.equal(work.uploadedImage, null);
	assert.equal(work.imageProvenance, '');
});

test('a delayed image upload cannot replace a later choice or return after sign-out', async () => {
	const pending: Array<(response: Response) => void> = [];
	const work = imageWork(async () => new Promise<Response>((resolve) => pending.push(resolve)));
	const first = work.selectImage(new File(['a'], 'first.png'));
	const second = work.selectImage(new File(['b'], 'second.png'));
	pending[1](Response.json(uploaded('second')));
	await second;
	pending[0](Response.json(uploaded('first')));
	await first;
	assert.equal(work.uploadedImage?.image_id, 'second');
	assert.equal(work.imageFileName, 'second.png');
	const third = work.selectImage(new File(['c'], 'third.png'));
	work.clearImage();
	pending[2](Response.json(uploaded('third')));
	await third;
	assert.equal(work.uploadedImage, null);
	assert.equal(work.imageUploading, false);
});

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
	const report = reports.at(-1);
	assert.ok(report);
	assert.deepEqual({ success: report.success, total: report.total, failures: report.failures }, {
		success: 1, total: 2,
		failures: [{ line: 2, input: 'failed line', message: 'schema_violation: 4 attempts' }]
	});
	assert.equal(report.retry?.prompt, 'drawn line\nfailed line');
	assert.equal(report.retry?.runId, 'batch-test');
	assert.deepEqual(report.retry?.failedLines, [2]);
	assert.deepEqual(report.retry?.pendingLines, [2]);
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

test('an edited sketch reaches authoring only for its description with sketching on', async () => {
	const requests: Array<{ text: string; options: { sketch: string; sketch_text?: string } }> = [];
	const work = createWorkState({
		apiFetch: async (path: string, init?: RequestInit) => {
			assert.equal(path, '/api/pipeline/variations');
			requests.push(JSON.parse(String(init?.body)));
			return new Response(JSON.stringify({ detail: 'request captured' }), { status: 400 });
		},
		batch: {}, demo: {}, refinementSession: { gridBusy: false },
		describeApiError: () => 'request captured', session: {}, history: () => ({}),
		canvasViewport: {}, canvasAspectId: () => 'square',
		models: { stage1Provider: () => 'openai', stage1Model: () => 'drawing',
			stage2Provider: () => 'openai', stage2Model: () => 'drawing', includeThinking: () => false },
	} as unknown as WorkStateDeps);
	work.adoptSketch('original sketch', null, 'same description', 'generated');
	work.sketchDraft = 'author edited sketch';
	await assert.rejects(work.authorDescription('same description'));
	assert.equal(requests.at(-1)?.options.sketch_text, 'author edited sketch');
	assert.equal(work.sketchText, 'original sketch');

	work.sketchMode = 'off';
	await assert.rejects(work.authorDescription('same description'));
	assert.equal(requests.at(-1)?.options.sketch, 'off');
	assert.equal(requests.at(-1)?.options.sketch_text, undefined);
	work.sketchMode = 'on';
	await assert.rejects(work.authorDescription('another description'));
	assert.equal(requests.at(-1)?.options.sketch_text, undefined);

	work.adoptSketch('new work sketch', null, 'new description', 'generated');
	assert.equal(work.sketchDraft, 'new work sketch');
	assert.equal(work.sketchEditing, false);
	await assert.rejects(work.authorDescription('new description'));
	assert.equal(requests.at(-1)?.options.sketch_text, 'new work sketch');
});

test('demo drawing sends its shared model to both stages even with a legacy stage 2 value', async () => {
	let body: { stage1_model: string; stage2_model: string } | null = null;
	const work = createWorkState({
		apiFetch: async (path: string, init?: RequestInit) => {
			assert.equal(path, '/api/paint/stream');
			body = JSON.parse(String(init?.body));
			return new Response(`${JSON.stringify({
				event: 'done', ddl: 'circle', thinking: null, svg: '<svg/>', score: { instructions: [] },
				elapsed_stage1_ms: 1, elapsed_stage2_ms: 1, elapsed_total_ms: 2,
				tokens_in_stage1: 1, tokens_out_stage1: 1, tokens_in_stage2: 1, tokens_out_stage2: 1,
			})}\n`, { headers: { 'Content-Type': 'application/x-ndjson' } });
		},
		batch: { resuming: false }, refinementSession: { gridBusy: false },
		demo: {
			clearInput: () => {}, latestResult: null,
			start: async (options: Parameters<WorkStateDeps['demo']['start']>[0]) => {
				try { await options.paintInstruction('demo prompt', { saveHistory: false }); }
				finally { options.onRunFinished(); }
			},
		},
		describeApiError: () => '', session: { updateGenerationCount: () => {} }, history: () => ({ clearSelection: () => {} }),
		canvasViewport: { fit: () => {} }, canvasAspectId: () => 'square', resetTargetScopedState: () => {}, showCanvas: () => {},
		models: { stage1Provider: () => 'chatgpt', stage1Model: () => 'drawing',
			stage2Provider: () => 'openai', stage2Model: () => 'legacy-other',
			includeThinking: () => false, available: () => [] },
	} as unknown as WorkStateDeps);
	await work.startDemo();
	assert.equal(body?.stage1_model, 'chatgpt:drawing');
	assert.equal(body?.stage2_model, 'chatgpt:drawing');
});
