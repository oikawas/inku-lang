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
	assert.deepEqual(recompositionLines(unchanged('nothing_to_move'), ja), ['この作品には構図の範囲が無い。', '構図の範囲を保って描き直しました。']);
	assert.deepEqual(recompositionLines(unchanged('unsolved'), en), ['There are too many combinations to find another composition.', 'Redrawn with the same composition ranges.']);
	for (const strings of [ja, en]) {
		assert.equal(recompositionLines(unchanged('binding_unavailable'), strings)[0], strings.recomposeReason('unknown'));
		assert.equal(recompositionLines(unchanged('invalid_request'), strings)[1], strings.recomposeKeptRanges);
	}
});

test('autonomous layout draws its parent DDL by principle even when the manual choice is chance', async () => {
	// Use the existing owner-test rune shim; no browser or renderer is started.
	installOwnerRuneShim();
	const { RefinementSessionState } = await import('./refinement-session.svelte.ts');
	const { createRefinementCoordinator } = await import('./refinement-coordinator.svelte.ts');
	const { colorCatalogOverride } = await import('../color-catalog/render.ts');
	const { wildOverride } = await import('../wild/render.ts');
	const { installCanvasFormatRegistry } = await import('../../plugins/system/canvas-aspect/index.ts');
	installCanvasFormatRegistry({ digest: 'fixture', registry: { schema: 'fixture', formats: [
		{ id: 'square', width_units: 1, height_units: 1 }, { id: 'vertical', width_units: 9, height_units: 16 }
	] } });
	const session = new RefinementSessionState({ ms: 0, start() {}, stop() {} });
	assert.equal(session.recomposeMode, 'principled');
	session.setRecomposeMode('chance');
	let requests = 0;
	let saves = 0;
	const coordinator = createRefinementCoordinator({
		session,
		work: { result: null, thinking: null, instructionLang: 'auto', pipelineCompatibilityError: async () => new Error('unexpected error') },
		models: { stage1: () => 'reader', stage2: () => 'performer' },
		seeds: { composition: (excluded: Set<number>) => { assert.ok(excluded.has(7)); return 42; } },
		render: { canvasAspectId: () => 'square' },
		catalog: { defaultId: () => 'default' },
		apiFetch: async (path: string, init?: RequestInit) => {
			requests += 1;
			assert.equal(path, '/api/compose');
			const payload = JSON.parse(String(init?.body));
			assert.equal(payload.ddl, 'saved parent instructions');
			assert.equal(payload.description, 'parent description');
			assert.equal(payload.sketch_text, 'the parent sketch prose');
			assert.equal(payload.recompose_mode, 'principled');
			assert.equal(payload.composition_seed, 42);
			assert.equal(payload.render_seed, '1553303611486672067');
			assert.equal(payload.canvas_aspect, 'vertical');
			assert.equal(payload.catalog_id, 'parent-catalog');
			assert.equal(payload.wild, true);
			assert.equal(payload.model, 'performer');
			assert.equal(payload.lineage_parent_node_id, 'parent-node');
			return new Response(JSON.stringify({ ddl: 'changed parent instructions', svg: '<svg/>', score: { instructions: [] } }));
		},
		pushHistory: async (item: HistoryItem, options?: SaveHistoryOptions) => {
			saves += 1;
			assert.equal(item.ddl, 'changed parent instructions');
			assert.equal(options?.derivationKind, 'layout_change');
			assert.equal(options?.lineageParentNodeId, 'parent-node');
			assert.equal(options?.historyVisibility, 'lineage_only');
			assert.deepEqual(options?.derivationMetadata, { autonomous_refine_mode: 'random', composition_seed: 42, recompose_mode: 'principled' });
			return { ...item, id: 'child-work', lineage_node_id: 'child-node' };
		}
	} as unknown as RefinementCoordinatorDeps);
	const result = await coordinator.composeLayoutGeneration({
		id: 'parent-work', ddl: 'saved parent instructions', catalogId: 'parent-catalog',
		renderSeed: '1553303611486672067', compositionSeed: 7, canvasAspectId: 'vertical',
		stage1Model: 'reader', instructionLang: 'en', ddlSourceOrigin: null
	}, 'parent description', {
		sketchText: 'the parent sketch prose',
		lineageParentNodeId: 'parent-node', derivationMetadata: { autonomous_refine_mode: 'random' },
		renderOverrides: { ...colorCatalogOverride('parent-catalog'), ...wildOverride(true) },
		historyVisibility: 'lineage_only', countGeneration: true
	});
	assert.equal(requests, 1);
	assert.equal(saves, 1);
	assert.equal(result.history_id, 'child-work');
	assert.equal(result.lineage_node_id, 'child-node');
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
				instructionLang: 'auto', sketchPayloadFor: () => ({}),
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
