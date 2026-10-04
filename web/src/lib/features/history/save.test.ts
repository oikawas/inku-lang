import assert from 'node:assert/strict';
import test from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import { saveHistoryItem } from './save.ts';

const item = (overrides: Partial<HistoryItem> = {}): HistoryItem => ({
	id: 'work-1',
	input: 'mist',
	ddl: 'mist ddl',
	score: { instructions: [] },
	svg: '',
	at: 10,
	...overrides
});

const jsonResponse = (value: unknown, status = 200): Response => new Response(
	JSON.stringify(value),
	{ status, headers: { 'Content-Type': 'application/json' } }
);

test('T-292/T-293: save owns the payload and selects the saved identity after refresh', async () => {
	const calls: Array<{ path: string; init?: RequestInit }> = [];
	const order: string[] = [];
	const saved = item({ id: 'saved-2', svg: '<svg>saved</svg>' });
	const result = await saveHistoryItem(item({
		ddl: '\u3000saved ddl\r\n',
		ddl_source_origin: 'legacy_expanded',
		render_seed: '7',
		composition_seed: '8',
		variation_seed: '9',
		variation_amplitude: 'medium',
		focus: 'center',
		compose_fallback_used: true,
		sketch_state: 'used'
	}), {
		selectSaved: true,
		countGeneration: true,
		sourceText: 'source',
		historyVisibility: 'normal',
		lineageParentNodeId: 'node-1',
		derivationKind: 'replay'
	}, {
		catalogId: 'catalog-default',
		catalogMode: 'auto',
		canvasAspectId: 'portrait',
		instructionLang: 'auto',
		uiLang: 'ja'
	}, {
		apiFetch: async (path, init) => {
			calls.push({ path, init });
			order.push('post');
			return jsonResponse(saved);
		},
		signedIn: () => true,
		ensureSvg: async () => { order.push('svg'); return '<svg>full</svg>'; },
		composeFallbackFor: () => 'retry',
		refreshCountedUser: async () => { order.push('user'); },
		activeHistoryId: () => 'work-active',
		currentOffset: () => 12,
		fetchOffset: async (offset, options) => {
			order.push(`fetch:${offset}:${options?.anchorId ?? ''}`);
			return true;
		},
		clearSelection: () => order.push('clear')
	});

	assert.equal(result?.id, 'saved-2');
	assert.deepEqual(order, ['svg', 'post', 'user', 'fetch:0:saved-2']);
	assert.equal(calls[0]?.path, '/api/history');
	const body = JSON.parse(String(calls[0]?.init?.body)) as Record<string, unknown>;
	assert.equal(body.svg, '<svg>full</svg>');
	assert.equal(body.ddl, '\u3000saved ddl\r\n');
	assert.equal(body.ddl_source_origin, 'legacy_expanded');
	assert.equal('expanded_ddl' in body, false);
	assert.equal(body.catalog_id, 'catalog-default');
	assert.equal(body.catalog_mode, 'auto');
	assert.equal(body.canvas_aspect, 'portrait');
	assert.equal(body.render_seed, '7');
	assert.equal(body.composition_seed, '8');
	assert.equal('variation_seed' in body, false);
	assert.equal('variation_amplitude' in body, false);
	assert.equal('focus' in body, false);
	assert.equal(body.compose_fallback, 'retry');
	assert.equal(body.sketch_state, 'used');
	assert.equal(body.source_text, 'source');
	assert.equal(body.lineage_parent_node_id, 'node-1');
	assert.equal(body.derivation_kind, 'replay');
});

test('T-292: old records preserve absent compose/sketch fields and reconcile the current offset', async () => {
	let body: Record<string, unknown> = {};
	const order: string[] = [];
	const result = await saveHistoryItem(item(), {}, {
		catalogId: 'default',
		catalogMode: 'fixed',
		canvasAspectId: 'landscape',
		instructionLang: 'en',
		uiLang: 'en'
	}, {
		apiFetch: async (_path, init) => {
			body = JSON.parse(String(init?.body)) as Record<string, unknown>;
			return new Response('', { status: 500 });
		},
		signedIn: () => true,
		ensureSvg: async () => '<svg/>',
		composeFallbackFor: () => null,
		refreshCountedUser: async () => order.push('user'),
		activeHistoryId: () => null,
		currentOffset: () => 24,
		fetchOffset: async (offset, options) => {
			order.push(`fetch:${offset}:${String(options?.preserveSelection)}`);
			return true;
		},
		clearSelection: () => order.push('clear')
	});

	assert.equal(result, null);
	assert.equal('compose_fallback' in body, false);
	assert.equal('sketch_state' in body, false);
	assert.deepEqual(order, ['fetch:24:true', 'clear']);
});

test('a save followed by more reconciles nothing unless it fails', async () => {
	const deps = (order: string[], response: () => Response) => ({
		apiFetch: async () => { order.push('post'); return response(); },
		signedIn: () => true,
		ensureSvg: async () => '<svg/>',
		composeFallbackFor: () => null,
		refreshCountedUser: async () => { order.push('user'); },
		activeHistoryId: () => 'work-active',
		currentOffset: () => 0,
		fetchOffset: async (offset: number, options?: { anchorId?: string }) => {
			order.push(`fetch:${offset}:${options?.anchorId ?? ''}`);
			return true;
		},
		clearSelection: () => order.push('clear')
	});
	const defaults = { catalogId: 'c', catalogMode: 'auto' as const, canvasAspectId: 'portrait', instructionLang: 'auto', uiLang: 'ja' };

	const kept: string[] = [];
	const saved = await saveHistoryItem(item(), { countGeneration: true, reconcile: false }, defaults,
		deps(kept, () => jsonResponse(item({ id: 'saved-3' }))));
	assert.equal(saved?.id, 'saved-3');
	assert.deepEqual(kept, ['post']);

	const refused: string[] = [];
	const failed = await saveHistoryItem(item(), { countGeneration: true, reconcile: false }, defaults,
		deps(refused, () => jsonResponse({ detail: 'no' }, 500)));
	assert.equal(failed, null);
	assert.deepEqual(refused, ['post', 'user', 'fetch:0:work-active']);
});
