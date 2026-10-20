import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';
import { ja } from '../../i18n/ja.ts';
import { en } from '../../i18n/en.ts';
import { saveRefinementCandidates } from './refinement-actions.ts';
import { layoutCandidateResult, recompositionLines, recompositionRequest, requestLayoutComposition, type Recomposition } from './recomposition.ts';
import type { VariationCandidate } from './refinement-session.svelte.ts';
import type { RefinementCoordinatorDeps } from './refinement-coordinator.svelte.ts';
import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { SaveHistoryOptions } from '../history/save.ts';

function installOwnerRuneShim(): void {
	const libRoot = new URL('../../', import.meta.url);
	registerHooks({ resolve(specifier, context, nextResolve) {
		if (specifier.startsWith('$lib/')) {
			const module = new URL(`${specifier.slice(5)}.ts`, libRoot);
			return nextResolve((existsSync(module) ? module : new URL(`${specifier.slice(5)}/index.ts`, libRoot)).href, context);
		}
		return nextResolve(specifier, context);
	} });
	(globalThis as unknown as Record<string, unknown>).$state = <T>(value: T) => value;
}

for (const { kind, count } of [{ kind: 'layout', count: 1 }, { kind: 'layout', count: 4 }, { kind: 'tool', count: 4 }] as const) {
	test(`${count}-option redraw saves the clicked selection before replacing ${kind} candidates`, async () => {
		installOwnerRuneShim();
		const host = globalThis as unknown as Record<string, unknown>;
		const previousWindow = host.window;
		host.window = { setTimeout: () => 0, clearTimeout: () => {} };
		try {
			const { RefinementSessionState } = await import('./refinement-session.svelte.ts');
			const { createRefinementCoordinator } = await import('./refinement-coordinator.svelte.ts');
			for (let failSecond of [false, true]) {
				const session = new RefinementSessionState({ ms: 0, start() {}, stop() {} });
				session.candidates = Array.from({ length: 4 }, (_, index) => ({
					id: `old-${index}`, label: `Old ${index}`, selected: index !== 1, saved: index === 3,
					result: {
						svg: '<svg/>', score: { instructions: [] }, ddl: `instructions-${index}`, thinking: null,
						lineage_parent_node_id: 'parent-node', derivation_kind: kind === 'layout' ? 'layout_change' : 'tool_change',
						derivation_metadata: { original_index: index }
					}
				}));
				let releaseSave!: () => void;
				const saveGate = new Promise<void>((resolve) => { releaseSave = resolve; });
				const saved: string[] = [];
				const events: string[] = [];
				let seed = 10;
				const coordinator = createRefinementCoordinator({
					session,
					work: {
						input: 'parent words', ddl: 'parent instructions', loading: false, thinking: null, displayedHistoryItem: null,
						result: { svg: '<svg/>', score: { instructions: [] }, history_id: 'parent-work', composition_seed: 7 },
						instructionLang: 'auto', sketchTextFor: () => null,
						confirmFallbackRefine: async () => true, currentRefineParent: () => null,
						paintTokensIn: () => null, paintTokensOut: () => null,
						pipelineCompatibilityError: async () => new Error('unexpected error')
					},
					models: { stage1: () => 'reader', stage2: () => 'performer' },
					seeds: { composition: () => ++seed },
					render: { canvasAspectId: () => 'square', wild: () => false, fanoutLimit: () => 1 },
					catalog: { defaultId: () => 'catalog', effectiveId: () => 'catalog', available: () => [], name: (id: string) => id },
					lineageParentId: () => 'parent-node', ensureVisibleLineageParentId: async () => 'parent-node',
					apiFetch: async (path: string) => {
						events.push(path);
						return new Response(JSON.stringify(path === '/api/tool-variants/plan' ? {
							tools: { chalk: { ja: 'チョーク', en: 'chalk' } },
							entries: Array.from({ length: 4 }, () => ({ tools: { '0': 'chalk' }, changes: [{ index: 0, from: 'pen', to: 'chalk' }] }))
						} : { ddl: 'new instructions', svg: '<svg/>', score: { instructions: [] } }));
					},
					pushHistory: async (item: HistoryItem, options: SaveHistoryOptions) => {
						saved.push(item.ddl!);
						events.push(`save:${item.ddl}`);
						assert.equal(options.lineageParentNodeId, 'parent-node');
						assert.equal(options.derivationKind, kind === 'layout' ? 'layout_change' : 'tool_change');
						if (saved.length === 1) await saveGate;
						if (failSecond && saved.length === 2) return null;
						return { ...item, id: `saved-${saved.length}` };
					}
				} as unknown as RefinementCoordinatorDeps);
				const redraw = () => kind === 'layout' ? coordinator.generateVariationCandidates('layout', count) : coordinator.generateToolCandidates();
				const pending = redraw();
				assert.deepEqual(events, ['save:instructions-0']);
				assert.equal(session.gridBusy, true);
				assert.equal(session.candidates.length, 4);
				// Selection after the click belongs to neither the saved snapshot nor the next round.
				session.toggleCandidate('old-1');
				await redraw();
				assert.deepEqual(events, ['save:instructions-0']);
				releaseSave();
				await pending;
				assert.deepEqual(saved, ['instructions-0', 'instructions-2']);
				if (failSecond) {
					assert.deepEqual(events, ['save:instructions-0', 'save:instructions-2']);
					assert.equal(session.candidates[0].saved, true);
					assert.equal(session.candidates[2].selected, true);
					assert.equal(session.candidates[2].saved, false);
					assert.ok(session.status);
					session.toggleCandidate('old-1');
					failSecond = false;
					await redraw();
					assert.deepEqual(saved, ['instructions-0', 'instructions-2', 'instructions-2']);
				}
				assert.equal(session.candidates.length, count);
				assert.ok(session.candidates.every((candidate) => !candidate.id.startsWith('old-') && !candidate.selected && !candidate.saved));
				assert.equal(session.gridBusy, false);
				assert.equal(events.filter((event) => event.startsWith('/api/')).length, kind === 'layout' ? count : 5);
			}
		} finally {
			host.window = previousWindow;
		}
	});
}

test('recomposition carries the requested mode and saves the DDL drawn with its seed and mode', async () => {
	const calls: Record<string, unknown>[] = [];
	const recomposition: Recomposition = {
		mode: 'chance', outcome: 'recomposed', answer: 'chance',
		moves: [{ layer: 0, from_key: 'cell-22', from: 'lower right', to_key: 'cell-00', to: 'upper left' }]
	};
	const data = await requestLayoutComposition({ ddl: 'original', composition_seed: 42 }, 'chance', undefined,
		async (path, init) => {
			assert.equal(path, '/api/compose');
			assert.equal(init?.method, 'POST');
			calls.push(JSON.parse(String(init?.body)));
			return new Response(JSON.stringify({ ddl: 'recomposed', svg: '<svg/>', score: { instructions: [] }, recomposition }));
		}, async () => new Error('unexpected error'));
	assert.deepEqual(calls, [{ ddl: 'original', composition_seed: 42, recompose_mode: 'chance' }]);
	assert.deepEqual(recompositionRequest(), {});
	assert.deepEqual(recompositionRequest('principled'), { recompose_mode: 'principled' });
	const legacy = layoutCandidateResult({ svg: '<svg/>', score: { instructions: [] } }, 'original', 42, 'principled');
	assert.equal(legacy.ddl, 'original');
	assert.deepEqual(recompositionLines(legacy.recomposition, en), []);
	const layout = layoutCandidateResult(data, 'original', 42, 'chance');
	const candidate: VariationCandidate = {
		id: 'comp-42', kind: 'layout', label: 'Another composition', selected: true,
		result: { ...layout, thinking: null, lineage_parent_node_id: 'parent', derivation_kind: 'layout_change',
			elapsed_stage1_ms: 0, elapsed_stage2_ms: 0, elapsed_total_ms: 0,
			tokens_in_stage1: null, tokens_out_stage1: null, tokens_in_stage2: null, tokens_out_stage2: null }
	};
	let writes = 0;
	assert.equal(await saveRefinementCandidates({ candidates: [candidate], sourceText: () => 'description', fallbackCatalogId: () => 'catalog' }, {
		saveHistory: async (item, options) => {
			writes += 1;
			assert.equal(item.ddl, 'recomposed');
			assert.equal(item.composition_seed, 42);
			assert.equal(options.derivationKind, 'layout_change');
			assert.equal(options.lineageParentNodeId, 'parent');
			assert.deepEqual(options.derivationMetadata, { composition_seed: 42, recompose_mode: 'chance' });
			return { ...item, id: 'saved' };
		}, isCurrentContext: () => true, markSaved: () => {}, isCurrentResult: () => false, adoptSavedIdentity: () => {}
	}), 'complete');
	assert.equal(writes, 1);
});

test('recomposition cards show human layer numbers and explain unchanged ranges in both languages', () => {
	assert.deepEqual(recompositionLines({ mode: 'principled', outcome: 'recomposed', moves: [
		{ layer: 0, from_key: null, from: '右下', to_key: 'cell-00', to: '左上' }
	] }, ja), ['1: 右下 → 左上']);
	const unchanged = (reason: string): Recomposition => ({ mode: 'principled', outcome: 'unchanged', reason, moves: [] });
	assert.deepEqual(recompositionLines(unchanged('nothing_to_move'), ja), ['この作品には構図の範囲が無い。', '指示書は変えず、配置の seed を変えて描き直しました。']);
	assert.deepEqual(recompositionLines(unchanged('unsolved'), en), ['There are too many combinations to find another composition.', 'Redrawn with a new composition seed; the instructions are unchanged.']);
	for (const strings of [ja, en]) {
		assert.equal(recompositionLines(unchanged('binding_unavailable'), strings)[0], strings.recomposeReason('unknown'));
		assert.equal(recompositionLines(unchanged('invalid_request'), strings)[1], strings.recomposeKeptRanges);
	}
});

test('manual layout draws a saved DDL without a description and saves its chosen chance mode', async () => {
	installOwnerRuneShim();
	const host = globalThis as unknown as Record<string, unknown>;
	const previousWindow = host.window;
	host.window = { setTimeout: () => 0, clearTimeout: () => {} };
	try {
		const { RefinementSessionState } = await import('./refinement-session.svelte.ts');
		const { createRefinementCoordinator } = await import('./refinement-coordinator.svelte.ts');
		const session = new RefinementSessionState({ ms: 0, start() {}, stop() {} });
		session.setRecomposeMode('chance');
		let requests = 0;
		let saves = 0;
		const coordinator = createRefinementCoordinator({
			session,
			work: {
				input: '', ddl: 'saved parent instructions', loading: false, thinking: null,
				result: { svg: '<svg/>', score: { instructions: [] }, composition_seed: 7, history_id: 'parent-work' },
				instructionLang: 'auto', sketchTextFor: () => null,
				confirmFallbackRefine: async () => true, currentRefineParent: () => null,
				paintTokensIn: () => null, paintTokensOut: () => null,
				pipelineCompatibilityError: async () => new Error('unexpected error')
			},
			models: { stage1: () => 'reader', stage2: () => 'performer' },
			seeds: { composition: (excluded: Set<number>) => { assert.ok(excluded.has(7)); return 42; } },
			render: { canvasAspectId: () => 'square', wild: () => false, fanoutLimit: () => 1 },
			catalog: { defaultId: () => 'catalog', effectiveId: () => 'catalog', available: () => [], name: (id: string) => id },
			lineageParentId: () => 'parent-node', ensureVisibleLineageParentId: async () => 'parent-node',
			apiFetch: async (path: string, init?: RequestInit) => {
				requests += 1;
				assert.equal(path, '/api/compose');
				const payload = JSON.parse(String(init?.body));
				assert.equal(payload.description, '');
				assert.equal(payload.ddl, 'saved parent instructions');
				assert.equal(payload.recompose_mode, 'chance');
				assert.equal(payload.composition_seed, 42);
				// The server forks the candidate from this saved work, with its
				// saved settings and seeds (SPEC §12.7.1).
				assert.equal(payload.work_id, 'parent-work');
				return new Response(JSON.stringify({ ddl: 'recomposed instructions', svg: '<svg/>', score: { instructions: [] } }));
			},
			pushHistory: async (item: HistoryItem, options?: SaveHistoryOptions) => {
				saves += 1;
				assert.equal(item.input, '');
				assert.equal(item.ddl, 'recomposed instructions');
				assert.equal(options?.derivationKind, 'layout_change');
				assert.equal(options?.lineageParentNodeId, 'parent-node');
				assert.deepEqual(options?.derivationMetadata, { composition_seed: 42, recompose_mode: 'chance' });
				return { ...item, id: 'saved-child' };
			}
		} as unknown as RefinementCoordinatorDeps);
		await coordinator.generateVariationCandidates('layout', 1);
		assert.equal(requests, 1);
		assert.equal(session.status, null);
		assert.equal(session.candidates.length, 1);
		session.toggleCandidate(session.candidates[0].id);
		assert.equal(await coordinator.saveSelectedVariationCandidates(), true);
		assert.equal(saves, 1);
		assert.equal(session.candidates[0].saved, true);
	} finally {
		host.window = previousWindow;
	}
});

test('a saved work opened beside an unfinished draft is refined from its own words and instructions', async () => {
	installOwnerRuneShim();
	const host = globalThis as unknown as Record<string, unknown>;
	const previousWindow = host.window;
	host.window = { setTimeout: () => 0, clearTimeout: () => {} };
	try {
		const { RefinementSessionState } = await import('./refinement-session.svelte.ts');
		const { createRefinementCoordinator } = await import('./refinement-coordinator.svelte.ts');
		const session = new RefinementSessionState({ ms: 0, start() {}, stop() {} });
		const bodies: Array<{ path: string; payload: Record<string, unknown> }> = [];
		const saved: HistoryItem[] = [];
		const coordinator = createRefinementCoordinator({
			session,
			// The library's refine opens the shown work and keeps the draft in the left pane.
			work: {
				input: 'draft words', ddl: 'draft instructions', loading: false, thinking: 'draft thinking',
				displayedHistoryItem: { id: 'shown-work', input: 'shown words', ddl: 'shown instructions', sketch_text: 'shown sketch', thinking: 'shown thinking' },
				result: { svg: '<svg/>', score: { instructions: [] }, composition_seed: 7, history_id: 'shown-work', render_color_catalog_id: 'catalog' },
				instructionLang: 'auto', sketchTextFor: () => 'draft sketch',
				confirmFallbackRefine: async () => true, currentRefineParent: () => null,
				paintTokensIn: () => null, paintTokensOut: () => null,
				pipelineCompatibilityError: async () => new Error('unexpected error')
			},
			models: { stage1: () => 'reader', stage2: () => 'performer' },
			seeds: { composition: () => 42 },
			render: { canvasAspectId: () => 'square', wild: () => false, fanoutLimit: () => 1 },
			catalog: { defaultId: () => 'catalog', effectiveId: () => 'catalog', available: () => [{ id: 'catalog' }, { id: 'other' }], name: (id: string) => id },
			lineageParentId: () => 'shown-node', ensureVisibleLineageParentId: async () => 'shown-node',
			apiFetch: async (path: string, init?: RequestInit) => {
				bodies.push({ path, payload: JSON.parse(String(init?.body)) });
				return new Response(JSON.stringify({ ddl: 'recomposed shown instructions', svg: '<svg/>', score: { instructions: [] } }));
			},
			pushHistory: async (item: HistoryItem) => { saved.push(item); return { ...item, id: `child-${saved.length}` }; }
		} as unknown as RefinementCoordinatorDeps);
		await coordinator.generateVariationCandidates('layout', 1);
		await coordinator.generateVariationCandidates('color', 1);
		assert.deepEqual(bodies.map(({ path, payload }) => [path, payload.ddl, payload.description ?? payload.input, payload.sketch_text ?? null]), [
			['/api/compose', 'shown instructions', 'shown words', 'shown sketch'],
			['/api/render-score', 'shown instructions', 'shown words', null]
		]);
		for (const candidate of session.candidates) session.toggleCandidate(candidate.id);
		assert.equal(await coordinator.saveSelectedVariationCandidates(), true);
		assert.deepEqual(saved.map((item) => [item.input, item.thinking]), [['shown words', 'shown thinking']]);
	} finally {
		host.window = previousWindow;
	}
});

test('a touch change draws four options in the chosen way, replaces them on the next press, and names what each sentence took', async () => {
	installOwnerRuneShim();
	const host = globalThis as unknown as Record<string, unknown>;
	const previousWindow = host.window;
	host.window = { setTimeout: () => 0, clearTimeout: () => {} };
	try {
		const { RefinementSessionState } = await import('./refinement-session.svelte.ts');
		const { createRefinementCoordinator } = await import('./refinement-coordinator.svelte.ts');
		const session = new RefinementSessionState({ ms: 0, start() {}, stop() {} });
		const requests: Array<{ path: string; payload: Record<string, unknown> }> = [];
		const tools = { chalk: { ja: 'チョーク', en: 'chalk' }, pen: { ja: 'ペン', en: 'pen' }, oil_paint: { ja: '油彩', en: 'oil paint' } };
		const plans: Record<string, unknown> = {
			uniform: { tools, entries: [{ tools: { '0': 'chalk', '1': 'chalk' }, changes: [{ index: 0, from: 'pen', to: 'chalk' }, { index: 1, from: 'oil_paint', to: 'chalk' }] }] },
			per_sentence: { tools, entries: [{ tools: { '0': 'oil_paint', '1': 'pen' }, changes: [{ index: 0, from: 'pen', to: 'oil_paint' }, { index: 1, from: 'oil_paint', to: 'pen' }] }] }
		};
		const coordinator = createRefinementCoordinator({
			session,
			work: {
				input: 'words', ddl: 'instructions', loading: false, thinking: null, displayedHistoryItem: null,
				result: { svg: '<svg/>', score: { instructions: [] }, history_id: 'shown-work' },
				instructionLang: 'auto', sketchTextFor: () => null,
				pipelineCompatibilityError: async () => new Error('unexpected error')
			},
			render: { fanoutLimit: () => 1 },
			lineageParentId: () => 'shown-node', ensureVisibleLineageParentId: async () => 'shown-node',
			apiFetch: async (path: string, init?: RequestInit) => {
				const payload = JSON.parse(String(init?.body));
				requests.push({ path, payload });
				if (path === '/api/tool-variants/plan') return new Response(JSON.stringify(plans[payload.mode as string]));
				return new Response(JSON.stringify({ ddl: 'retouched', svg: '<svg/>', score: { instructions: [] } }));
			}
		} as unknown as RefinementCoordinatorDeps);
		assert.equal(session.toolMode, 'uniform');
		await coordinator.generateToolCandidates();
		assert.deepEqual(session.candidates.map((candidate) => [candidate.label, candidate.details, candidate.result.derivation_kind, candidate.result.derivation_metadata]), [
			['チョーク', [], 'tool_change', { tool_mode: 'uniform', tools: { '0': 'chalk', '1': 'chalk' } }]
		]);
		session.setToolMode('per_sentence');
		await coordinator.generateToolCandidates();
		assert.deepEqual(requests.map(({ path, payload }) => [path, payload.mode, payload.tools ?? null]), [
			['/api/tool-variants/plan', 'uniform', null],
			['/api/render-tool-variant', 'uniform', { '0': 'chalk', '1': 'chalk' }],
			['/api/tool-variants/plan', 'per_sentence', null],
			['/api/render-tool-variant', 'per_sentence', { '0': 'oil_paint', '1': 'pen' }]
		]);
		// The second press replaces the options shown.
		assert.deepEqual(session.candidates.map((candidate) => [candidate.label, candidate.details, candidate.result.derivation_kind, candidate.result.derivation_metadata]), [
			['文ごと 1', ['1: ペン → 油彩', '2: 油彩 → ペン'], 'tool_change', { tool_mode: 'per_sentence', tools: { '0': 'oil_paint', '1': 'pen' } }]
		]);
		assert.equal(session.candidates[0].result.ddl, 'retouched');
	} finally {
		host.window = previousWindow;
	}
});
