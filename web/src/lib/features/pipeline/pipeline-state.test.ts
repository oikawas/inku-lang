import assert from 'node:assert/strict';
import test from 'node:test';

import { PipelineApi, PipelineApiError, pipelineDiagnostics, type PipelineView } from './api.ts';
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
	let historyLinked = true;
	let holdHistoryLink = false;
	let historyLinkFailureStatus: number | null = null;
	let releaseHistoryLink: (() => void) | null = null;
	const api = {
		start: async () => { calls.push({ method: 'start' }); return view({ busy: true }); },
		load: async () => { calls.push({ method: 'load' }); return loadCount++ === 0 ? patch : ready; },
		command: async (_active: PipelineView, command: unknown) => {
			calls.push({ method: 'command', value: command });
			if (rejectNextCommand) throw new PipelineApiError(409, { code: 'authority_conflict', current_revision: '7' });
			return (command as { tag: string }).tag === 'approve_patch' ? view({ ...ready, busy: true }) : rendered;
		},
		authorDdl: async (_active: PipelineView, source: string, options: unknown) => {
			calls.push({ method: 'authorDdl', value: { source, options } });
			if (rejectNextCommand) throw new PipelineApiError(409, { code: 'authority_conflict', current_revision: '7' });
			return rendered;
		},
		historyLink: async (historyId: string) => {
			calls.push({ method: 'historyLink', value: historyId });
			if (holdHistoryLink) await new Promise<void>((resolve) => { releaseHistoryLink = resolve; });
			if (historyLinkFailureStatus !== null) throw new PipelineApiError(historyLinkFailureStatus, { code: 'pipeline_history_lookup_failed' });
			if (!historyLinked) throw new PipelineApiError(404, { code: 'pipeline_history_not_found' });
			return { variation_id: 'variation-history', revision: '1' };
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
	assert.deepEqual(calls.at(-1), {
		method: 'authorDdl',
		value: { source: 'edited circle', options: { canvas_aspect: 'square' } },
	});
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

	await controller.selectHistory('history-managed-without-list-hint');
	assert.deepEqual(calls.at(-1), {
		method: 'historyLink',
		value: 'history-managed-without-list-hint',
	});
	await controller.fromDdl('managed lineage edit');
	assert.deepEqual(calls.at(-1), {
		method: 'forkHistory',
		value: { historyId: 'history-managed-without-list-hint', options: { canvas_aspect: 'square' } },
	});

	historyLinked = false;
	await controller.selectHistory('history-old');
	await controller.fromDdl('legacy edit');
	assert.deepEqual(calls.at(-1), { method: 'forkLegacy', value: 'history-old' });

	controller.markLinkedHistory('history-reopened');
	assert.deepEqual(pipelineDiagnostics(controller.current, {
		upstream_diagnostics: [{ kind: 'upstream' }],
		downstream_diagnostics: [{ kind: 'downstream' }],
		resource_omissions: [{ kind: 'resource' }],
		relation_omissions: [{ kind: 'relation' }],
		render_diagnostics: {
			rendered_instruction_indices: [0],
			diagnostics: [{ instruction_index: 2, reason: 'fill_clip_limit_exceeded', disposition: 'omitted' }],
		},
		resource_execution: {
			omissions: [{ owner: { instruction_index: 3 }, failure: 'budget_exceeded', disposition: 'omitted' }],
			relation_omissions: [{ instruction_index: 4, reason: 'target_omitted' }],
		},
	}).map((diagnostic) => diagnostic.channel), [
		'upstream',
		'downstream',
		'resource',
		'relation',
		'render',
		'resource',
		'relation',
	]);

	let requestPath = '';
	let requestBody: Record<string, unknown> = {};
	const transport = new PipelineApi(async (path, init) => {
		requestPath = path;
		requestBody = JSON.parse(String(init?.body)) as Record<string, unknown>;
		return new Response(JSON.stringify(ready), {
			headers: { 'Content-Type': 'application/json' },
		});
	});
	await transport.authorDdl(ready, 'edited with new paper', { canvas_aspect: 'hd_monitor', wild: true });
	assert.equal(requestPath, '/api/pipeline/executions/execution-1/author-ddl');
	assert.deepEqual(requestBody, {
		source: 'edited with new paper',
		expected_revision: '1',
		options: { canvas_aspect: 'hd_monitor', wild: true },
	});

	historyLinked = true;
	holdHistoryLink = true;
	const waitingSelection = controller.selectHistory('history-waiting');
	const waitingAuthoring = controller.fromDdl('edit while history lookup waits');
	await Promise.resolve();
	assert.deepEqual(calls.at(-1), { method: 'historyLink', value: 'history-waiting' });
	releaseHistoryLink?.();
	assert.equal(await waitingSelection, true);
	await waitingAuthoring;
	assert.deepEqual(calls.at(-1), {
		method: 'forkHistory',
		value: { historyId: 'history-waiting', options: { canvas_aspect: 'square' } },
	});

	holdHistoryLink = false;
	historyLinkFailureStatus = 503;
	await assert.rejects(controller.selectHistory('history-lookup-failed'), (error: unknown) =>
		error instanceof PipelineApiError && error.status === 503);
	const callsBeforeFailedAuthoring = calls.length;
	await assert.rejects(controller.fromDescription('must not become new work'), (error: unknown) =>
		error instanceof PipelineApiError && error.status === 503);
	assert.equal(calls.length, callsBeforeFailedAuthoring);

	historyLinkFailureStatus = null;
	holdHistoryLink = true;
	const canceledSelection = controller.selectHistory('history-authoring-canceled');
	const authoringAbort = new AbortController();
	const canceledAuthoring = controller.fromDdl('must not fork after cancel', {}, authoringAbort.signal);
	const callsBeforeCanceledRelease = calls.length;
	authoringAbort.abort();
	releaseHistoryLink?.();
	assert.equal(await canceledSelection, true);
	await assert.rejects(canceledAuthoring, (error: unknown) => error instanceof DOMException && error.name === 'AbortError');
	assert.equal(calls.length, callsBeforeCanceledRelease);

	const expiredAfterLookup = controller.selectHistory('history-expired-after-lookup');
	const authoringAfterExpiredLookup = controller.fromDdl('must not start in the resume gap');
	const expireBeforeAuthoringResumes = expiredAfterLookup.then(() => controller.clear());
	const callsBeforeExpiredLookupRelease = calls.length;
	releaseHistoryLink?.();
	assert.equal(await expiredAfterLookup, true);
	await expireBeforeAuthoringResumes;
	await assert.rejects(authoringAfterExpiredLookup, /pipeline_history_selection_superseded/);
	assert.equal(calls.length, callsBeforeExpiredLookupRelease);

	const superseded = controller.selectHistory('history-superseded');
	const supersededAuthoring = controller.fromDescription('must not start after selection expires');
	const callsBeforeSupersededRelease = calls.length;
	controller.clear();
	releaseHistoryLink?.();
	assert.equal(await superseded, false);
	await assert.rejects(supersededAuthoring, /pipeline_history_selection_superseded/);
	assert.equal(controller.current, null);
	assert.equal(calls.length, callsBeforeSupersededRelease);
});
