import assert from 'node:assert/strict';
import { test } from 'node:test';
import { HistoryManagerState, refreshDerived, works } from './history-manager-harness.ts';

const settle = () => new Promise<void>((resolve) => setImmediate(resolve));

test('a selected-work start permits newer pages through the filtered listing back to its latest work', async () => {
	const calls: URLSearchParams[] = [];
	const manager = new HistoryManagerState(async (path) => {
		const params = new URL(path, 'https://inku.invalid').searchParams;
		calls.push(params);
		const offset = params.has('anchor_id') ? 7 : Number(params.get('offset'));
		return Response.json({
			items: works(Number(params.get('limit'))).map((item, index) => ({ ...item, id: `work-${offset + index}` })),
			offset, total: 30,
		});
	}, () => {});
	manager.libraryInitialized = true;
	manager.pageSize = 3;
	manager.search = 'blue';
	manager.starredOnly = true;
	manager.selectedIds = ['keep-checked'];
	manager.openWith([], 30, 0, 'work-7');
	await settle();
	refreshDerived(manager);
	assert.equal(manager.activeItems[0].id, 'work-7', 'the selected work still starts the initial page');
	assert.equal(manager.focusRequest?.id, 'work-7');

	for (const offset of [4, 1, 0]) {
		manager.setPage(-1);
		await settle();
		refreshDerived(manager);
		assert.equal(calls.at(-1)!.get('offset'), String(offset));
		assert.equal(manager.activeItems[0].id, `work-${offset}`);
		assert.equal(calls.at(-1)!.get('q'), 'blue');
		assert.equal(calls.at(-1)!.get('starred'), 'true');
		assert.deepEqual(manager.selectedIds, ['keep-checked']);
		assert.equal(manager.focusRequest, null, 'paging does not refocus the original selected work');
	}
	const atLatest = calls.length;
	manager.setPage(-1);
	await settle();
	assert.equal(calls.length, atLatest, 'the latest page cannot move into a negative offset');
	manager.setPage(1);
	await settle();
	assert.equal(calls.at(-1)!.get('offset'), '3', 'older navigation remains available after reaching the latest work');
});
