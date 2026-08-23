import assert from 'node:assert/strict';
import test from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import { replayHistoryItem } from './replay.ts';

const item = (overrides: Partial<HistoryItem> = {}): HistoryItem => ({
	id: 'work-1',
	input: 'mist',
	ddl: 'mist ddl',
	score: { instructions: [], canvas: 'square' },
	svg: '<svg>old</svg>',
	at: 10,
	...overrides
});

test('T-294: replay keeps recorded seeds, work payload, source, and version mismatch', async () => {
	let path = '';
	let body: Record<string, unknown> = {};
	const comparison = await replayHistoryItem(item({
		render_seed: '17',
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
			return new Response('<svg>new</svg>');
		},
		apiError: async (response) => new Error(`HTTP ${response.status}`),
		ensureSvg: async (work) => work.svg
	});

	assert.ok(comparison);
	assert.equal(path, '/api/render-svg');
	assert.equal(body.render_seed, 17);
	assert.equal(body.composition_seed, '23');
	assert.equal(body.catalog_id, 'catalog-recorded');
	assert.equal(body.work_id, 'work-1');
	assert.equal(comparison.source, 'lineage');
	assert.equal(comparison.originalSvg, '<svg>old</svg>');
	assert.equal(comparison.replayedSvg, '<svg>new</svg>');
	assert.equal(comparison.provisionalSeed, null);
	assert.equal(comparison.versionMessage, 'engine-old->engine-new');
});

test('T-294: a seedless old work gets provisional zero without inventing a placement seed', async () => {
	let body: Record<string, unknown> = {};
	const comparison = await replayHistoryItem(item({
		render_seed: null,
		composition_seed: null,
		seed_text: null,
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
			return new Response('<svg>new</svg>');
		},
		apiError: async (response) => new Error(`HTTP ${response.status}`),
		ensureSvg: async () => '<svg>old</svg>'
	});

	assert.ok(comparison);
	assert.equal(body.render_seed, 0);
	assert.equal(body.composition_seed, null);
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
		apiFetch: async () => new Response('<svg>new</svg>'),
		apiError: async (response) => new Error(`HTTP ${response.status}`),
		ensureSvg: async () => { ensured = true; return '<svg>old</svg>'; },
		acceptRendered: () => false
	});
	assert.equal(comparison, null);
	assert.equal(ensured, false);
});
