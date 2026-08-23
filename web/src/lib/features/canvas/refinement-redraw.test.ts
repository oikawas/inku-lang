import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { CanvasAspectId } from '../../plugins/system/canvas-aspect/index.ts';
import type { CurrentWorkResult, PaintOptions } from '../run/current-work.ts';
import {
	projectRefinementRedrawResult,
	runLayoutRedraw,
	runReadingRedraw,
	runTouchRedraw
} from './refinement-redraw.ts';

function result(overrides: Partial<CurrentWorkResult> = {}): CurrentWorkResult {
	return {
		ddl: 'expanded ddl',
		thinking: 'thinking',
		svg: '<svg id="old"/>',
		score: { instructions: [], canvas: 'portrait' },
		render_seed: 11,
		composition_seed: 0,
		render_hash: 'render-hash',
		render_hash_short: 'short',
		history_id: 'history-1',
		history_at: 100,
		lineage_node_id: 'node-1',
		elapsed_stage1_ms: 3,
		elapsed_stage2_ms: 5,
		elapsed_total_ms: 8,
		tokens_in_stage1: 1,
		tokens_out_stage1: 2,
		tokens_in_stage2: 4,
		tokens_out_stage2: 6,
		...overrides
	};
}

const aspect = 'portrait' as CanvasAspectId;

test('T-327: touch redraw preserves seed zero, request references, and existing result-read timing', async () => {
	const requests: Array<{ path: string; init?: RequestInit }> = [];
	const exclusions: number[][] = [];
	const current = result();
	let latest = current;
	const redrawn = await runTouchRedraw({
		current,
		canvasAspectId: aspect,
		parentNodeId: 'parent-1',
		workReference: { work_id: 'history-1' },
		renderPayload: { catalog_id: 'catalog-1', wild: false }
	}, {
		apiFetch: async (path, init) => {
			requests.push({ path, init });
			latest = result({ render_seed: 99, stage1_model: 'late/current' });
			return new Response('<svg id="new"/>');
		},
		apiError: async () => new Error('unexpected'),
		createRenderSeed: (excluded) => {
			exclusions.push([...excluded]);
			return 22;
		},
		currentResult: () => latest
	});

	assert.deepEqual(exclusions, [[11]]);
	assert.equal(requests[0]?.path, '/api/render-svg');
	assert.equal(requests[0]?.init?.method, 'POST');
	assert.deepEqual(JSON.parse(String(requests[0]?.init?.body)), {
		score: current.score,
		canvas_aspect: 'portrait',
		render_seed: 22,
		composition_seed: 0,
		work_id: 'history-1',
		catalog_id: 'catalog-1',
		wild: false
	});
	assert.deepEqual(
		{
			svg: redrawn.svg,
			renderSeed: redrawn.render_seed,
			compositionSeed: redrawn.composition_seed,
			renderHash: redrawn.render_hash,
			historyId: redrawn.history_id,
			lineageNodeId: redrawn.lineage_node_id,
			parentNodeId: redrawn.lineage_parent_node_id,
			kind: redrawn.derivation_kind,
			metadata: redrawn.derivation_metadata,
			stage1Model: redrawn.stage1_model
		},
		{
			svg: '<svg id="new"/>',
			renderSeed: 22,
			compositionSeed: 0,
			renderHash: null,
			historyId: null,
			lineageNodeId: null,
			parentNodeId: 'parent-1',
			kind: 'touch_change',
			metadata: { render_seed_from: 99, render_seed_to: 22 },
			stage1Model: 'late/current'
		}
	);
});

test('T-328: layout redraw excludes the current seed and passes canonical Paint options', async () => {
	const calls: Array<{ source: string; options: PaintOptions }> = [];
	const renderOverrides = { colorCatalog: { selected: 'catalog-1' } };
	const painted = result({ source_ddl: 'source ddl', composition_seed: 44 });
	const redrawn = await runLayoutRedraw({
		source: 'source words',
		current: result({ composition_seed: 33 }),
		canvasAspectId: aspect,
		renderOverrides,
		parentNodeId: 'parent-1'
	}, {
		createCompositionSeed: (excluded) => {
			assert.deepEqual([...excluded], [33]);
			return 44;
		},
		paint: async (source, options) => {
			calls.push({ source, options });
			return painted;
		}
	});

	assert.equal(redrawn, painted);
	assert.deepEqual(calls, [{
		source: 'source words',
		options: {
			compositionSeed: 44,
			historyInput: 'source words',
			sourceText: 'source words',
			canvasAspectId: aspect,
			renderOverrides,
			lineageParentNodeId: 'parent-1',
			derivationKind: 'layout_change',
			derivationMetadata: { composition_seed: 44 }
		}
	}]);
	assert.deepEqual(projectRefinementRedrawResult(redrawn), {
		ddl: 'source ddl',
		expandedDdl: 'expanded ddl',
		thinking: 'thinking',
		result: redrawn,
		elapsedStage1Ms: 3,
		elapsedStage2Ms: 5,
		elapsedTotalMs: 8,
		tokensInStage1: 1,
		tokensOutStage1: 2,
		tokensInStage2: 4,
		tokensOutStage2: 6
	});
});

test('T-329: reading redraw creates one interpretation seed and preserves Paint options', async () => {
	const calls: Array<{ source: string; options: PaintOptions }> = [];
	let seedCalls = 0;
	const painted = result({ source_ddl: null });
	const redrawn = await runReadingRedraw({
		source: 'source words',
		canvasAspectId: aspect,
		renderOverrides: {},
		parentNodeId: null
	}, {
		createInterpretationSeed: () => {
			seedCalls += 1;
			return 'interpretation-1';
		},
		paint: async (source, options) => {
			calls.push({ source, options });
			return painted;
		}
	});

	assert.equal(redrawn, painted);
	assert.equal(seedCalls, 1);
	assert.deepEqual(calls, [{
		source: 'source words',
		options: {
			historyInput: 'source words',
			sourceText: 'source words',
			canvasAspectId: aspect,
			renderOverrides: {},
			interpretationSeed: 'interpretation-1',
			lineageParentNodeId: null,
			derivationKind: null,
			derivationMetadata: { interpretation_seed: 'interpretation-1' }
		}
	}]);
	assert.equal(projectRefinementRedrawResult(redrawn).ddl, 'expanded ddl');
});

test('T-330: a rejected touch response uses the existing error conversion and returns no result', async () => {
	const expected = new Error('render rejected');
	let converted = 0;
	await assert.rejects(
		runTouchRedraw({
			current: result({ composition_seed: null }),
			canvasAspectId: aspect,
			parentNodeId: null,
			workReference: {},
			renderPayload: {}
		}, {
			apiFetch: async () => new Response('no', { status: 409 }),
			apiError: async () => { converted += 1; return expected; },
			createRenderSeed: () => 22,
			currentResult: () => { throw new Error('must not map a rejected response'); }
		}),
		(error) => error === expected
	);
	assert.equal(converted, 1);
});
