import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HistoryManagerState, works } from './history-manager-harness.ts';

test('returning to an in-flight page makes that answer the latest question', async () => {
	const pending: Array<(response: Response) => void> = [];
	const manager = new HistoryManagerState(() => new Promise((resolve) => pending.push(resolve)), () => {});
	manager.pageSize = 2;
	manager.page = 0;
	const a = manager.fetch();
	manager.page = 1;
	const b = manager.fetch();
	manager.page = 0;
	await manager.fetch();
	assert.equal(pending.length, 2);
	pending[1]({ ok: true, json: async () => ({ items: works(2, 'old'), total: 4 }) } as Response);
	await b;
	assert.equal(manager.activeItems.length, 0);
	pending[0]({ ok: true, json: async () => ({ items: works(2, 'latest'), total: 4 }) } as Response);
	await a;
	assert.equal(manager.activeItems[0].id, 'latest-0');
	assert.equal(manager.loading, false);
});

test('a changed query cannot accept an earlier response even before another request', async () => {
	let resolve!: (response: Response) => void;
	const manager = new HistoryManagerState(() => new Promise((done) => { resolve = done; }), () => {});
	const pending = manager.fetch();
	manager.search = 'new query';
	resolve({ ok: true, json: async () => ({ items: works(1, 'old'), total: 1 }) } as Response);
	await pending;
	assert.equal(manager.activeItems.length, 0);
});
