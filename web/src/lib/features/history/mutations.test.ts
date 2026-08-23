import assert from 'node:assert/strict';
import test from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import { HistoryMutations, type HistoryBulkMutationPath } from './mutations.ts';

const work = (overrides: Partial<HistoryItem> = {}): HistoryItem => ({
	id: 'work-1',
	input: 'mist',
	ddl: 'mist',
	score: { instructions: [] },
	svg: '<svg/>',
	at: 1,
	starred: false,
	for_revision: false,
	for_share: false,
	share_group_id: null,
	...overrides
});

const jsonResponse = (body: unknown, status = 200): Response => new Response(
	JSON.stringify(body),
	{ status, headers: { 'Content-Type': 'application/json' } }
);

function harness(responder: (path: string, init?: RequestInit) => Promise<Response>) {
	const calls: Array<{ path: string; init?: RequestInit }> = [];
	const projections: string[] = [];
	const refreshes: string[] = [];
	const warnings: string[] = [];
	let current: HistoryItem | null = work();
	let focusedLineageNodeId: string | null = 'node-1';

	const manager = {
		starredOnly: false,
		forRevisionOnly: false,
		forShareOnly: false,
		selectedIds: ['work-1'],
		async fetch() { refreshes.push('manager'); }
	};
	const browsing = {
		items: [work()],
		offset: 0,
		cursor: 0,
		windowSize: 2,
		starredOnly: false,
		forRevisionOnly: false,
		forShareOnly: false,
		manager,
		applyStarState(item: { id?: string; starred?: boolean; note?: string | null }) {
			projections.push(`browse:star:${String(item.starred)}:${String(item.note)}`);
		},
		applyForRevisionState(item: { id?: string; for_revision?: boolean }) {
			projections.push(`browse:revision:${String(item.for_revision)}`);
		},
		applyForShareState(item: { id?: string; for_share?: boolean; share_group_id?: string | null }) {
			projections.push(`browse:share:${String(item.for_share)}:${String(item.share_group_id)}`);
		},
		clearStarredFilter() { this.starredOnly = false; projections.push('filter:star:clear'); },
		clearForRevisionFilter() { this.forRevisionOnly = false; projections.push('filter:revision:clear'); },
		clearForShareFilter() { this.forShareOnly = false; projections.push('filter:share:clear'); },
		clearSelection() { this.cursor = -1; projections.push('selection:clear'); },
		async syncToItem(item: HistoryItem) { projections.push(`selection:sync:${item.id}`); },
		async fetchOffset(offset: number, options?: { anchorId?: string }) {
			refreshes.push(`strip:${offset}:${options?.anchorId ?? ''}`);
			if (this.cursor < 0 && this.items.length > 0) this.cursor = 0;
			return true;
		},
		async fetchTrashPage() { refreshes.push('trash'); }
	};

	const mutations = new HistoryMutations({
		apiFetch: async (path, init) => {
			calls.push({ path, init });
			return await responder(path, init);
		},
		signedIn: () => true,
		browsing,
		currentItem: () => current,
		setCurrentItem: (item) => {
			current = item;
			projections.push(`current:${item?.id ?? 'none'}:${String(item?.starred)}:${String(item?.for_revision)}:${String(item?.for_share)}:${String(item?.trashed)}`);
		},
		applyLineageStarState: (item) => projections.push(`lineage:star:${String(item.starred)}:${String(item.note)}`),
		applyLineageForRevisionState: (item) => projections.push(`lineage:revision:${String(item.for_revision)}`),
		applyLineageForShareState: (item) => projections.push(`lineage:share:${String(item.for_share)}:${String(item.share_group_id)}`),
		focusedLineageNodeId: () => focusedLineageNodeId,
		reloadLineage: async (id) => { refreshes.push(`lineage:${id}`); },
		displayCurrentItem: (item) => { current = item; projections.push(`display:${item.id}`); },
		clearCurrentWork: () => { current = null; projections.push('display:clear'); },
		warn: (message) => warnings.push(message)
	});

	return {
		mutations,
		calls,
		projections,
		refreshes,
		warnings,
		browsing,
		manager,
		current: () => current,
		setCurrent: (item: HistoryItem | null) => { current = item; },
		setFocusedLineageNodeId: (id: string | null) => { focusedLineageNodeId = id; }
	};
}

test('T-284/T-285: each mark owns its endpoint, optimistic projection, and server projection', async () => {
	const cases = [
		{
			name: 'star',
			path: '/api/history/work-1/star',
			body: { starred: true },
			updated: work({ starred: true, note: 'kept' }),
			run: (owner: HistoryMutations) => owner.toggleStar(work())
		},
		{
			name: 'revision',
			path: '/api/history/work-1/for-revision',
			body: { for_revision: true },
			updated: work({ for_revision: true }),
			run: (owner: HistoryMutations) => owner.toggleForRevision(work())
		},
		{
			name: 'share',
			path: '/api/history/work-1/for-share',
			body: { for_share: true },
			updated: work({ for_share: true, share_group_id: 'group-7' }),
			run: (owner: HistoryMutations) => owner.toggleForShare(work())
		}
	] as const;

	for (const item of cases) {
		const h = harness(async () => jsonResponse(item.updated));
		await item.run(h.mutations);
		assert.equal(h.calls.length, 1, item.name);
		assert.equal(h.calls[0]?.path, item.path, item.name);
		assert.equal(h.calls[0]?.init?.method, 'PATCH', item.name);
		assert.deepEqual(JSON.parse(String(h.calls[0]?.init?.body)), item.body, item.name);
		assert.match(h.projections[0] ?? '', new RegExp(`browse:${item.name}`), `${item.name} did not project optimistically first`);
		assert.ok(h.projections.some((entry) => entry.startsWith(`lineage:${item.name}`)), `${item.name} missed lineage`);
	}
});

test('T-285/T-287: failures roll back, and optimistic share never invents a destination', async () => {
	const h = harness(async () => { throw new Error('offline'); });
	const original = work({ for_share: false, share_group_id: 'group-old' });
	h.setCurrent(original);
	await h.mutations.toggleForShare(original);
	assert.equal(h.projections[0], 'browse:share:true:group-old');
	assert.ok(h.projections.includes('browse:share:false:group-old'));
	assert.deepEqual(h.warnings, ['failed to update the share mark']);
});

test('T-286: leaving an active mark filter clears it and refreshes only the affected listings', async () => {
	const h = harness(async () => jsonResponse(work({ starred: false })));
	h.browsing.starredOnly = true;
	h.manager.starredOnly = true;
	await h.mutations.toggleStar(work({ starred: true }));
	assert.ok(h.projections.includes('filter:star:clear'));
	assert.deepEqual(h.refreshes, ['strip:0:work-1', 'manager']);
});

test('T-288: bulk lifecycle mutations keep endpoint, refresh, and displayed-work outcomes together', async () => {
	const cases: Array<{
		path: HistoryBulkMutationPath;
		expectedProjection: string;
	}> = [
		{ path: '/api/history/trash', expectedProjection: 'current:work-1:false:false:false:true' },
		{ path: '/api/history/restore', expectedProjection: 'selection:sync:work-1' },
		{ path: '/api/history/permanent-delete', expectedProjection: 'current:none:undefined:undefined:undefined:undefined' }
	];

	for (const item of cases) {
		const h = harness(async () => new Response(null, { status: 204 }));
		await h.mutations.postIds(item.path, ['work-1']);
		assert.equal(h.calls[0]?.path, item.path);
		assert.deepEqual(JSON.parse(String(h.calls[0]?.init?.body)), { ids: ['work-1'] });
		assert.ok(h.projections.includes(item.expectedProjection), item.path);
		assert.deepEqual(h.refreshes.slice(0, 4), ['strip:0:', 'trash', 'manager', 'lineage:node-1']);
	}
});

test('T-288: removing the displayed work reseats the canvas on the refreshed strip', async () => {
	const h = harness(async () => new Response(null, { status: 204 }));
	h.browsing.items = [work({ id: 'work-2' })];
	h.browsing.cursor = 0;
	await h.mutations.postIds('/api/history/trash', ['work-1']);
	assert.ok(h.projections.includes('display:work-2'));
});
