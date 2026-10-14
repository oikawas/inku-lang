import assert from 'node:assert/strict';
import test from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import { replayHistoryItem, saveReplayComparison, type ReplayComparison } from './replay.ts';

const item = (overrides: Partial<HistoryItem> = {}): HistoryItem => ({
	id: 'work-1',
	input: 'mist',
	ddl: 'mist ddl',
	score: { instructions: [], canvas: 'square' },
	svg: '<svg>old</svg>',
	at: 10,
	...overrides
});

const renderedResponse = () => new Response(JSON.stringify({
	svg: '<svg>new</svg>', render_engine_version: 'engine-new',
	render_hash: 'rh3:new', svg_sha256: 'new-svg-sha256', render_seed: '0',
}));

test('T-294: replay keeps recorded seeds, work payload, source, and version mismatch', async () => {
	let path = '';
	let body: Record<string, unknown> = {};
	const comparison = await replayHistoryItem(item({
		// Past 2^53: Number() would send back 1553303611486672100.
		render_seed: '1553303611486672067',
		composition_seed: '23',
		render_engine_version: 'engine-old',
		render_color_catalog_id: 'catalog-recorded'
	}), 'lineage', {
		effectiveCatalogId: 'catalog-default',
		effectiveCanvasAspectId: 'portrait',
		currentRenderEngineVersion: 'engine-new',
		renderPayload: (_work, catalogId) => ({ work_id: 'work-1', catalog_id: catalogId }),
		versionMismatchMessage: (recorded, current) => `${recorded}->${current}`,
		versionNotRecordedMessage: (current) => `missing:${current}`
	}, {
		apiFetch: async (nextPath, init) => {
			path = nextPath;
			body = JSON.parse(String(init?.body)) as Record<string, unknown>;
			return renderedResponse();
		},
		apiError: async (response) => new Error(`HTTP ${response.status}`),
		ensureSvg: async (work) => work.svg
	});

	assert.ok(comparison);
	assert.equal(path, '/api/render-score');
	assert.equal(body.input, 'mist');
	assert.equal(body.ddl, 'mist ddl');
	assert.equal(body.render_seed, '1553303611486672067');
	assert.equal(body.composition_seed, '23');
	assert.equal(body.catalog_id, 'catalog-recorded');
	assert.equal(body.work_id, 'work-1');
	assert.equal(comparison.source, 'lineage');
	assert.equal(comparison.originalSvg, '<svg>old</svg>');
	assert.equal(comparison.replayedSvg, '<svg>new</svg>');
	assert.equal(comparison.provisionalSeed, null);
	assert.equal(comparison.versionMessage, 'engine-old->engine-new');
	assert.equal(comparison.renderHash, 'rh3:new');
	assert.equal(comparison.svgSha256, 'new-svg-sha256');
	assert.equal(comparison.replayedItem.id, undefined);
	assert.equal(comparison.replayedItem.render_engine_version, 'engine-new');
});

test('T-294: a seedless old work gets provisional zero without inventing a placement seed', async () => {
	let body: Record<string, unknown> = {};
	const comparison = await replayHistoryItem(item({
		render_seed: null,
		composition_seed: null,
		seed_text: '   ',
		render_engine_version: null
	}), 'canvas', {
		effectiveCatalogId: 'default',
		effectiveCanvasAspectId: 'portrait',
		currentRenderEngineVersion: 'engine-new',
		renderPayload: () => ({}),
		versionMismatchMessage: () => 'mismatch',
		versionNotRecordedMessage: (current) => `missing:${current}`
	}, {
		apiFetch: async (_path, init) => {
			body = JSON.parse(String(init?.body)) as Record<string, unknown>;
			return renderedResponse();
		},
		apiError: async (response) => new Error(`HTTP ${response.status}`),
		ensureSvg: async () => '<svg>old</svg>'
	});

	assert.ok(comparison);
	assert.equal(body.render_seed, 0);
	assert.equal(body.composition_seed, null);
	assert.equal(body.seed_text, null);
	assert.equal(comparison.provisionalSeed, 0);
	assert.equal(comparison.versionMessage, 'missing:engine-new');
});

test('T-294: a stale target is rejected before the original SVG is fetched', async () => {
	let ensured = false;
	const comparison = await replayHistoryItem(item(), 'canvas', {
		effectiveCatalogId: 'default',
		effectiveCanvasAspectId: 'square',
		currentRenderEngineVersion: null,
		renderPayload: () => ({}),
		versionMismatchMessage: () => 'mismatch',
		versionNotRecordedMessage: () => 'missing'
	}, {
		apiFetch: async () => renderedResponse(),
		apiError: async (response) => new Error(`HTTP ${response.status}`),
		ensureSvg: async () => { ensured = true; return '<svg>old</svg>'; },
		acceptRendered: () => false
	});
	assert.equal(comparison, null);
	assert.equal(ensured, false);
});

test('saving a replay child blocks repeated clicks and keeps the same key after a failed save', async () => {
	const comparison: ReplayComparison = {
		source: 'lineage', originalSvg: '<svg>old</svg>', replayedSvg: '<svg>new</svg>',
		recordedVersion: '74', currentVersion: '75', versionMessage: null, provisionalSeed: null,
		originalItem: item({ lineage_node_id: 'parent-node' }),
		replayedItem: item({ id: undefined, svg: '<svg>new</svg>' }),
		renderHash: 'rh3:new', svgSha256: 'new-svg-sha256', saveKey: 'save-key',
		saving: false, savedItem: null, saveError: null,
	};
	let fail!: (error: Error) => void;
	const options: unknown[] = [];
	const first = saveReplayComparison(comparison, async (_work, nextOptions) => {
		options.push(nextOptions);
		return new Promise((_resolve, reject) => { fail = reject; });
	}, 'Save failed');
	assert.equal(comparison.saving, true);
	assert.equal(await saveReplayComparison(comparison, async () => { assert.fail('duplicate POST'); }, 'Save failed'), null);
	fail(new Error('The displayed performance changed.'));
	assert.equal(await first, null);
	assert.equal(comparison.saveError, 'The displayed performance changed.');
	assert.equal(comparison.saving, false);
	const child = item({ id: 'child-work', lineage_parent_node_id: 'parent-node' });
	assert.equal(await saveReplayComparison(comparison, async (_work, nextOptions) => {
		options.push(nextOptions);
		return child;
	}, 'Save failed'), child);
	assert.deepEqual(options[0], options[1]);
	assert.deepEqual(options[1], {
		countGeneration: false, historyVisibility: 'normal', lineageParentNodeId: 'parent-node',
		derivationKind: 'replay', replayWorkId: 'work-1', replayRenderHash: 'rh3:new',
		replaySvgSha256: 'new-svg-sha256', idempotencyKey: 'save-key', rejectOnFailure: true,
	});
	assert.equal(comparison.saveError, null);
	assert.equal(await saveReplayComparison(comparison, async () => { assert.fail('saved twice'); }, 'Save failed'), child);
});
