import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HistoryManagerState, refreshDerived, works } from './history-manager-harness.ts';

const settle = () => new Promise<void>((resolve) => setImmediate(resolve));

test('preview resizing keeps the first work on a later page through opening, closing and paging', async () => {
	const calls: URLSearchParams[] = [];
	const manager = new HistoryManagerState(async (path) => {
		const params = new URL(path, 'https://inku.invalid').searchParams;
		calls.push(params);
		const offset = Number(params.get('offset'));
		return Response.json({ items: works(Number(params.get('limit'))).map((item, i) => ({ ...item, id: `work-${offset + i}` })), total: 300 });
	}, () => {});
	manager.pageSize = 42;
	manager.page = 1;
	manager.activeTotal = 300;
	manager.selectedIds = ['work-45'];
	refreshDerived(manager);
	await manager.fetch();
	for (const size of [36, 42]) {
		refreshDerived(manager);
		manager.setPageSize(size);
		await settle();
		assert.equal(calls.at(-1)!.get('offset'), '42');
		assert.equal(manager.activeItems[0].id, 'work-42');
		assert.deepEqual(manager.selectedIds, ['work-45']);
	}
	refreshDerived(manager);
	manager.setPage(manager.page + 1);
	await settle();
	assert.equal(calls.at(-1)!.get('offset'), '84');
	refreshDerived(manager);
	manager.setPage(manager.page - 1);
	await settle();
	assert.equal(calls.at(-1)!.get('offset'), '42');
	manager.setLatestPage();
	await settle();
	assert.equal(calls.at(-1)!.get('offset'), '0');
});

test('a larger viewport keeps the start even when a full newer page cannot fit before it', async () => {
	const calls: URLSearchParams[] = [];
	const manager = new HistoryManagerState(async (path) => {
		const params = new URL(path, 'https://inku.invalid').searchParams;
		calls.push(params);
		return Response.json({ items: works(Number(params.get('limit'))), total: 300 });
	}, () => {});
	manager.startOffset = 7;
	manager.pageSize = 36;
	manager.page = 1;
	manager.activeTotal = 300;
	manager.focusRequest = { id: 'selected', visit: 1 };
	refreshDerived(manager);
	manager.setPageSize(100);
	await settle();
	assert.equal(calls.at(-1)!.get('offset'), '43');
	assert.ok(manager.startOffset >= 0);
	assert.equal(manager.focusRequest?.id, 'selected');
});
