import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

const libRoot = new URL('../../', import.meta.url);
registerHooks({ resolve(specifier, context, nextResolve) {
	if (specifier.startsWith('$lib/')) {
		const file = new URL(`${specifier.slice(5)}.ts`, libRoot);
		return nextResolve((existsSync(file) ? file : new URL(`${specifier.slice(5)}/index.ts`, libRoot)).href, context);
	}
	return nextResolve(specifier, context);
} });
const identity = <T>(value: T): T => value;
const host = globalThis as unknown as Record<string, unknown>;
host.$state = Object.assign(identity, { raw: identity });
host.$derived = Object.assign(identity, { by: <T>(read: () => T): T => read() });
host.window = globalThis;
const { RefinementSessionState } = await import('./refinement-session.svelte.ts');
const { createRefinementCoordinator } = await import('./refinement-coordinator.svelte.ts');

test('four composition-form forks retain the parent settings and only selected execution is saved', async () => {
	const calls: Array<{ path: string; body: Record<string, unknown> }> = [];
	let sequence = 0;
	const view = (id: number, done = false) => ({ execution_id: `e${id}`, variation_id: `v${id}`, authority: { revision: '1' },
		description: 'poem', document: null, phase: { tag: done ? 'completed' : 'score_ready' }, busy: false,
		delivery: { score: { instructions: [] } }, rendered: null,
		result: done ? { ddl: 'line', svg: '<svg/>', score: { instructions: [] }, thinking: null } : null });
	const apiFetch = async (path: string, init?: RequestInit) => {
		const body = init?.body ? JSON.parse(String(init.body)) as Record<string, unknown> : {};
		calls.push({ path, body });
		let data: unknown;
		if (path === '/api/pipeline/history/parent') data = { variation_id: 'vp', revision: '1' };
		else if (path === '/api/pipeline/history/parent/fork') data = view(++sequence);
		else if (path.endsWith('/commands')) data = view(Number(path.match(/e(\d+)/)?.[1]), true);
		else if (path.endsWith('/save')) data = { history_id: 'saved', history_at: 1 };
		else throw new Error(path);
		return new Response(JSON.stringify(data), { status: 200, headers: { 'Content-Type': 'application/json' } });
	};
	const session = new RefinementSessionState();
	const work = {
		result: { history_id: 'parent', ddl: 'parent ddl', svg: '<svg/>', score: { instructions: [] },
			stage1_model: 'm', stage2_model: 'm', render_seed: 123, render_color_catalog_id: 'default' },
		displayedHistoryItem: { id: 'parent', input: 'poem', ddl: 'parent ddl', sketch_text: 'reading',
			description_ddl: { composition: { answer: { form: 'one_corner' } } } },
		input: 'poem', ddl: 'parent ddl', thinking: null, instructionLang: 'ja', loading: false,
		paintTokensIn: () => 0, paintTokensOut: () => 0,
	};
	const coordinator = createRefinementCoordinator({
		apiFetch, apiError: async () => new Error('request failed'), work, session,
		history: { syncToItem: async () => {} }, models: { stage1: () => 'm', stage2: () => 'm' },
		catalog: { defaultId: () => 'default', effectiveId: () => 'default', available: () => [], name: () => 'default' },
		render: { canvasAspectId: () => 'square', wild: () => false, fanoutLimit: () => 4 },
		seeds: { composition: () => 1 }, lineageParentId: () => 'node', ensureVisibleLineageParentId: async () => 'node',
		pushHistory: async () => { throw new Error('must save execution'); }, resetTargetScopedState: () => {},
	} as unknown as Parameters<typeof createRefinementCoordinator>[0]);
	await coordinator.generateCompositionFormCandidates('bands', 4);
	assert.equal(session.candidates.length, 4);
	const forks = calls.filter((call) => call.path.endsWith('/fork'));
	assert.equal(forks.length, 4);
	for (const fork of forks) {
		const options = fork.body.options as Record<string, unknown>;
		assert.equal(options.composition_form, 'bands');
		assert.equal(options.sketch_text, 'reading');
		assert.equal(options.render_seed, 123);
		assert.equal(options.catalog_mode, 'fixed');
		assert.equal(options.save_history, false);
	}
	session.toggleCandidate(session.candidates[1].id);
	assert.equal(await coordinator.saveSelectedVariationCandidates(), true);
	assert.deepEqual(calls.filter((call) => call.path.endsWith('/save')).map((call) => call.path), ['/api/pipeline/executions/e2/save']);
});
