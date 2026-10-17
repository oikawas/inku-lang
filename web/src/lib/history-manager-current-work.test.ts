import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HistoryManagerState, refreshDerived, works } from './history-manager-harness.ts';

const settle = () => new Promise<void>((resolve) => setImmediate(resolve));
const json = (value: unknown) => new Response(JSON.stringify(value));

test('opening at the current work keeps its exact filtered start across measurement and paging', async () => {
	const calls: URLSearchParams[] = [];
	let release!: (response: Response) => void;
	const manager = new HistoryManagerState(async (path) => {
		const params = new URL(path, 'https://inku.invalid').searchParams;
		calls.push(params);
		if (params.has('anchor_id')) return new Promise((resolve) => { release = resolve; });
		return json({ items: works(Number(params.get('limit'))), total: 30 });
	}, () => {});
	manager.libraryInitialized = true;
	manager.search = 'blue';
	manager.searchChanged('blue');
	await settle();
	manager.starredOnly = true;
	manager.selectedIds = ['keep-checked'];
	manager.openWith([], 30, 0, 'selected');
	assert.equal(calls.at(-1)!.get('q'), 'blue');
	assert.equal(calls.at(-1)!.get('starred'), 'true');
	const beforeMeasure = calls.length;
	manager.setPageSize(3);
	assert.equal(calls.length, beforeMeasure, 'measurement cannot supersede the pending position');
	release(json({ items: [{ ...works(1)[0], id: 'selected' }], offset: 7 }));
	await settle();
	refreshDerived(manager);
	assert.equal(manager.startOffset, 7);
	assert.equal(manager.offset, 7);
	assert.equal(calls.at(-1)!.get('offset'), '7');
	assert.equal(calls.at(-1)!.get('limit'), '3');
	assert.equal(manager.focusRequest?.id, 'selected');
	assert.deepEqual(manager.selectedIds, ['keep-checked']);
	manager.setPage(1);
	await settle();
	assert.equal(calls.at(-1)!.get('offset'), '10');
	manager.setLatestPage();
	await settle();
	assert.equal(calls.at(-1)!.get('offset'), '0');
});

test('a filtered-out canvas work preserves the library page and a late visit cannot replace a newer one', async () => {
	const pending: { params: URLSearchParams; resolve: (response: Response) => void }[] = [];
	const manager = new HistoryManagerState((path) => new Promise((resolve) => {
		pending.push({ params: new URL(path, 'https://inku.invalid').searchParams, resolve });
	}), () => {});
	manager.libraryInitialized = true;
	manager.page = 2;
	manager.pageSize = 3;
	manager.activeTotal = 30;
	refreshDerived(manager);
	manager.openWith([], 30, 0, 'excluded');
	pending[0].resolve(json({ items: works(1), offset: 6 }));
	await settle();
	assert.equal(pending[1].params.get('offset'), '6');
	pending[1].resolve(json({ items: works(3), total: 30 }));
	await settle();
	assert.equal(manager.page, 2);
	assert.equal(manager.focusRequest, null);
	manager.openWith([], 30, 0, 'old-visit');
	manager.openWith([], 30, 0, 'new-visit');
	pending[3].resolve(json({ items: [{ ...works(1)[0], id: 'new-visit' }], offset: 11 }));
	await settle();
	pending[4].resolve(json({ items: works(3), total: 30 }));
	await settle();
	pending[2].resolve(json({ items: [{ ...works(1)[0], id: 'old-visit' }], offset: 1 }));
	await settle();
	assert.equal(manager.startOffset, 11);
	assert.equal(manager.focusRequest?.id, 'new-visit');
});

test('a removed anchored page returns to available works instead of keeping an empty start', async () => {
	const offsets: string[] = [];
	const manager = new HistoryManagerState(async (path) => {
		const params = new URL(path, 'https://inku.invalid').searchParams;
		if (params.has('anchor_id')) return json({ items: [{ ...works(1)[0], id: 'selected' }], offset: 7 });
		offsets.push(params.get('offset')!);
		return json({ items: params.get('offset') === '0' ? works(5) : [], total: 5 });
	}, () => {});
	manager.openWith([], 9, 0, 'selected');
	await settle();
	assert.deepEqual(offsets, ['7', '0']);
	assert.equal(manager.startOffset, 0);
	assert.equal(manager.activeItems.length, 5);
	assert.equal(manager.focusRequest, null);
});
