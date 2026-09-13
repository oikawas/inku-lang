import assert from 'node:assert/strict';
import test from 'node:test';

import { PipelineApiError, type PipelineView } from './api.ts';
import { PipelineController } from './controller.ts';

function view(overrides: Partial<PipelineView> = {}): PipelineView {
	return {
		execution_id: 'execution-1',
		variation_id: 'variation-1',
		authority: { revision: '0', origin: 'stage1_generated', authority: 'description_authoritative' },
		description: 'moon over a mountain',
		document: null,
		phase: { tag: 'running' },
		delivery: null,
		busy: false,
		rendered: null,
		result: null,
		...overrides,
	};
}

test('normal authoring keeps approval, fork, stale CAS, and legacy parent on the shared pipeline', async () => {
	const calls: Array<{ method: string; value?: unknown }> = [];
	const patch = view({ busy: false, document: { source: 'circle', language: 'ja' }, phase: {
		tag: 'awaiting_patch_approval',
		candidate: { source: 'circle\nbackground' },
		proposal_digest: 'proposal-1',
	} });
	const ready = view({
		authority: { revision: '1', origin: 'stage1_generated', authority: 'ddl_authoritative' },
		document: { source: 'circle\nbackground', language: 'ja' },
		phase: { tag: 'ready' },
		delivery: { score: {}, upstream_diagnostics: [], downstream_diagnostics: [], resource_omissions: [], relation_omissions: [] },
	});
	const rendered = view({
		...ready,
		result: {
			svg: '<svg/>', score: { instructions: [] }, history_id: 'history-new',
			elapsed_stage1_ms: 1, elapsed_stage2_ms: 2, elapsed_total_ms: 3,
			tokens_in_stage1: null, tokens_out_stage1: null,
			tokens_in_stage2: null, tokens_out_stage2: null,
		},
	});
	const forked = view({
		execution_id: 'execution-2', variation_id: 'variation-2',
		authority: { revision: '0', origin: 'stage1_generated', authority: 'description_authoritative' },
		result: rendered.result,
	});
	let loadCount = 0;
	let rejectNextCommand = false;
	const api = {
		start: async () => { calls.push({ method: 'start' }); return view({ busy: true }); },
		load: async () => { calls.push({ method: 'load' }); return loadCount++ === 0 ? patch : ready; },
		command: async (_active: PipelineView, command: unknown) => {
			calls.push({ method: 'command', value: command });
			if (rejectNextCommand) throw new PipelineApiError(409, { code: 'authority_conflict', current_revision: '7' });
			return (command as { tag: string }).tag === 'approve_patch' ? view({ ...ready, busy: true }) : rendered;
		},
		forkDescription: async (_active: PipelineView, _description: string, options: unknown) => {
			calls.push({ method: 'forkDescription', value: options });
			return forked;
		},
		forkHistory: async (historyId: string, _kind: string, _text: string, options: unknown) => {
			calls.push({ method: 'forkHistory', value: { historyId, options } });
			return forked;
		},
		forkLegacy: async (historyId: string) => { calls.push({ method: 'forkLegacy', value: historyId }); return forked; },
	};
	const observed: Array<PipelineView | null> = [];
	const controller = new PipelineController(
		api as never,
		() => ({ canvas_aspect: 'square' }),
		(next) => observed.push(next),
		async () => undefined,
	);

	const waiting = await controller.fromDescription('moon over a mountain');
	assert.equal(waiting.phase.tag, 'awaiting_patch_approval');
	assert.equal(calls.some((call) => call.method === 'command' && (call.value as { tag?: string })?.tag === 'perform'), false);

	const completed = await controller.approvePatch();
	assert.equal(completed.result?.history_id, 'history-new');
	assert.deepEqual(calls.filter((call) => call.method === 'command').map((call) => call.value), [
		{ tag: 'approve_patch', expected_revision: '0', proposal_digest: 'proposal-1' },
		{ tag: 'perform' },
	]);

	await controller.fromDescription('moon over a mountain');
	assert.equal(calls.at(-1)?.method, 'forkDescription');
	assert.deepEqual(calls.at(-1)?.value, { canvas_aspect: 'square' });
	rejectNextCommand = true;
	await assert.rejects(controller.fromDdl('edited circle'), (error: unknown) =>
		error instanceof PipelineApiError && error.status === 409 && error.detail.current_revision === '7');
	assert.equal(controller.current?.variation_id, 'variation-2');
	assert.equal(observed.at(-1)?.variation_id, 'variation-2');

	rejectNextCommand = false;
	const loadsBeforeHistorySelection = calls.filter((call) => call.method === 'load').length;
	controller.markLinkedHistory('history-revision-1');
	assert.equal(controller.current, null);
	assert.equal(calls.filter((call) => call.method === 'load').length, loadsBeforeHistorySelection);
	await controller.fromDdl('managed history edit');
	assert.deepEqual(calls.at(-1), {
		method: 'forkHistory',
		value: { historyId: 'history-revision-1', options: { canvas_aspect: 'square' } },
	});

	controller.markLegacy('history-old');
	await controller.fromDdl('legacy edit');
	assert.deepEqual(calls.at(-1), { method: 'forkLegacy', value: 'history-old' });
});
