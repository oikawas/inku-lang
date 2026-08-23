import assert from 'node:assert/strict';
import test from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { LineageNode } from './types.ts';
import { focusSavedLineageChild, promoteLineageNode, saveLineageNote } from './lineage-actions.ts';

const item = (overrides: Partial<HistoryItem> = {}): HistoryItem => ({
	id: 'work-1',
	input: 'mist',
	ddl: 'mist ddl',
	score: { instructions: [] },
	svg: '<svg/>',
	at: 10,
	...overrides
});

const jsonResponse = (value: unknown, status = 200): Response => new Response(
	JSON.stringify(value),
	{ status, headers: { 'Content-Type': 'application/json' } }
);

test('T-296: saved child focus clears a hiding filter before canvas and lineage adoption', async () => {
	const order: string[] = [];
	let attempts = 0;
	await focusSavedLineageChild('work-2', 'node-2', {
		fetchOffset: async (_offset, options) => {
			attempts += 1;
			order.push(`fetch:${options?.anchorId}`);
			return attempts > 1;
		},
		filtered: () => true,
		clearFilters: () => order.push('clear'),
		items: () => [item({ id: 'work-2' })],
		displayCurrentItem: (work) => order.push(`display:${work.id}`),
		loadLineage: async (id) => { order.push(`lineage:${id}`); },
		missingIdentityError: () => new Error('identity'),
		missingWorkError: () => new Error('work')
	});
	assert.deepEqual(order, ['fetch:work-2', 'clear', 'fetch:work-2', 'display:work-2', 'lineage:node-2']);
});

test('T-296: promote drops a response after the current target changes', async () => {
	let version = 1;
	const effects: string[] = [];
	await promoteLineageNode({ id: 'node-1' }, {
		apiFetch: async () => {
			version = 2;
			return jsonResponse(item({ id: 'work-1' }));
		},
		contextVersion: () => version,
		currentItem: () => item(),
		setCurrentItem: () => effects.push('set'),
		activeHistoryId: () => 'work-1',
		currentOffset: () => 0,
		syncToItem: async () => { effects.push('sync'); },
		fetchOffset: async () => { effects.push('fetch'); return true; },
		loadLineage: async () => { effects.push('lineage'); }
	});
	assert.deepEqual(effects, []);
});

test('T-296: note save uses the star projection before lineage reload', async () => {
	const node: LineageNode = { id: 'node-1', state: 'active', at: 1, history: item({ starred: true }) };
	const order: string[] = [];
	let body: Record<string, unknown> = {};
	await saveLineageNote(node, `  ${'n'.repeat(250)}  `, {
		apiFetch: async (_path, init) => {
			body = JSON.parse(String(init?.body)) as Record<string, unknown>;
			return jsonResponse(item({ starred: true, note: 'saved' }));
		},
		contextVersion: () => 1,
		applyStarState: (work) => order.push(`apply:${work.note}`),
		loadLineage: async (id) => { order.push(`lineage:${id}`); }
	});
	assert.equal(body.starred, true);
	assert.equal(String(body.note).length, 240);
	assert.deepEqual(order, ['apply:saved', 'lineage:node-1']);
});
