import assert from 'node:assert/strict';
import test from 'node:test';
import { HistoryManagerState, works } from './history-manager-harness.ts';

test('lineage mode opens without a chronological listing request', async () => {
	const requests: string[] = [];
	const manager = new HistoryManagerState(async (path) => { requests.push(path); return new Response('{}'); }, () => {});
	manager.setDisplayMode('lineage');
	manager.openWith(works(10), 10, 0, null);
	await manager.fetch();
	assert.deepEqual(requests, []);
});
