import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { HistoryItem } from '../../historyManagerState.svelte.ts';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = stateShim;
runeHost.$derived = identity;

const { HistoryBrowsingState } = await import('./browsing-state.svelte.ts');

type PendingRequest = {
	path: string;
	init?: RequestInit;
	resolve: (response: Response) => void;
};

function work(id: string, at = 1): HistoryItem {
	return {
		id,
		input: id,
		ddl: null,
		score: { instructions: [] },
		svg: '',
		at
	};
}

function jsonResponse(value: unknown, status = 200): Response {
	return new Response(JSON.stringify(value), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function deferredTransport() {
	const requests: PendingRequest[] = [];
	const apiFetch = (path: string, init?: RequestInit): Promise<Response> => new Promise((resolve) => {
		requests.push({ path, init, resolve });
	});
	return { apiFetch, requests };
}

function makeState(apiFetch: (path: string, init?: RequestInit) => Promise<Response>) {
	const controls = {
		signedIn: true,
		drawing: false,
		visible: true,
		locked: false,
		currentId: null as string | null,
		currentItem: null as HistoryItem | null,
		now: 10_000,
		starredNotices: 0,
		otherNotices: 0
	};
	const state = new HistoryBrowsingState({
		apiFetch,
		signedIn: () => controls.signedIn,
		drawing: () => controls.drawing,
		visible: () => controls.visible,
		navigationLocked: () => controls.locked,
		currentHistoryId: () => controls.currentId,
		currentItem: () => controls.currentItem,
		managerPageSize: () => 5,
		now: () => controls.now,
		onStarredFilterCleared: () => { controls.starredNotices += 1; },
		onOtherFilterCleared: () => { controls.otherNotices += 1; }
	});
	void state.resize(3);
	return { state, controls };
}

test('T-275: only the latest strip request settles items, offset, and busy state', async () => {
	const { apiFetch, requests } = deferredTransport();
	const { state, controls } = makeState(apiFetch);

	const first = state.fetchOffset(0);
	const second = state.fetchOffset(3);
	assert.equal(state.fetchInFlight, 2);
	assert.match(requests[0]?.path ?? '', /^\/api\/history\?offset=0&limit=3&include_svg=false$/);
	assert.match(requests[1]?.path ?? '', /^\/api\/history\?offset=3&limit=3&include_svg=false$/);

	requests[1]?.resolve(jsonResponse({ items: [work('newer')], total: 8, offset: 3 }));
	await second;
	requests[0]?.resolve(jsonResponse({ items: [work('stale')], total: 8, offset: 0 }));
	await first;

	assert.deepEqual(state.items.map((item) => item.id), ['newer']);
	assert.equal(state.offset, 3);
	assert.equal(state.fetchInFlight, 0);

	controls.signedIn = false;
	assert.equal(await state.fetchOffset(0), false);
	assert.deepEqual(state.items, []);
	assert.equal(state.total, 0);
	assert.equal(state.offset, 0);

	controls.signedIn = true;
	const invalidated = state.fetchOffset(0);
	state.clear();
	requests[2]?.resolve(jsonResponse({ items: [work('after-reset')], total: 1, offset: 0 }));
	await invalidated;
	assert.deepEqual(state.items, []);
	assert.deepEqual(state.manager.activeItems, []);
});

test('T-276/T-278: anchored selection clears strip filters and seeds the one manager', async () => {
	const calls: string[] = [];
	const { state, controls } = makeState(async (path) => {
		calls.push(path);
		if (path.includes('starred=true')) {
			return jsonResponse({ items: [], total: 1, offset: 0 });
		}
		return jsonResponse({ items: [work('anchor')], total: 1, offset: 0 });
	});
	state.starredOnly = true;
	state.forRevisionOnly = true;
	state.forShareOnly = true;
	controls.currentItem = work('anchor');

	await state.syncToItem(controls.currentItem);

	assert.equal(state.cursor, 0);
	assert.equal(state.starredOnly, false);
	assert.equal(state.forRevisionOnly, false);
	assert.equal(state.forShareOnly, false);
	assert.equal(controls.starredNotices, 1);
	assert.equal(controls.otherNotices, 0);
	assert.match(calls.at(-1) ?? '', /anchor_id=anchor/);

	await state.fetchOffset(0);
	assert.deepEqual(state.manager.activeItems.map((item) => item.id), ['anchor']);
	assert.equal(state.manager.activeTotal, 1);
});

test('T-277: navigation applies the canonical target after a page arrives', async () => {
	const { state, controls } = makeState(async (path) => {
		const offset = Number(new URL(path, 'https://inku.invalid').searchParams.get('offset'));
		return jsonResponse({
			items: [work(`w-${offset}`), work(`w-${offset + 1}`), work(`w-${offset + 2}`)],
			total: 6,
			offset
		});
	});
	await state.fetchOffset(0);
	state.select(2);

	const older = await state.move('older');
	assert.equal(older?.id, 'w-3');
	assert.equal(state.offset, 3);
	assert.equal(state.cursor, 0);

	controls.locked = true;
	assert.equal(await state.move('newer'), null);
	controls.locked = false;

	await state.resize(4);
	assert.equal(state.windowSize, 4);
	assert.equal(state.offset, 0);
});

test('T-279: external refresh probes first, skips an unchanged list, and fetches a changed one', async () => {
	const calls: string[] = [];
	let serverState = { total: 1, newest_at: 1, newest_id: 'held' };
	const { state, controls } = makeState(async (path) => {
		calls.push(path);
		if (path === '/api/history/state') return jsonResponse(serverState);
		return jsonResponse({ items: [work(serverState.newest_id, serverState.newest_at)], total: serverState.total, offset: 0 });
	});
	await state.fetchOffset(0);
	calls.length = 0;
	controls.now = 20_000;

	await state.refreshExternal();
	assert.deepEqual(calls, ['/api/history/state']);

	serverState = { total: 2, newest_at: 2, newest_id: 'fresh' };
	controls.now = 26_000;
	await state.refreshExternal();
	assert.equal(calls[1], '/api/history/state');
	assert.match(calls[2] ?? '', /^\/api\/history\?/);
	assert.equal(state.items[0]?.id, 'fresh');
});

test('T-279: a failed external state probe falls through to the safe listing fetch', async () => {
	const calls: string[] = [];
	const { state, controls } = makeState(async (path) => {
		calls.push(path);
		if (path === '/api/history/state') return jsonResponse({}, 503);
		return jsonResponse({ items: [work('fallback')], total: 1, offset: 0 });
	});
	controls.now = 20_000;

	await state.refreshExternal();

	assert.deepEqual(calls.slice(0, 1), ['/api/history/state']);
	assert.match(calls[1] ?? '', /^\/api\/history\?/);
	assert.equal(state.items[0]?.id, 'fallback');
});

test('T-280: save/run refresh and named mark projections update browsing state', async () => {
	const calls: string[] = [];
	const { state, controls } = makeState(async (path) => {
		calls.push(path);
		return jsonResponse({ items: [work('active')], total: 4, offset: 0 });
	});
	await state.fetchOffset(0);
	controls.currentId = 'active';
	await state.refreshAfterServerSave();
	assert.equal(state.cursor, 0);

	state.applyStarState({ id: 'active', starred: true, note: 'kept' });
	state.applyForRevisionState({ id: 'active', for_revision: true });
	state.applyForShareState({ id: 'active', for_share: true, share_group_id: 'group-a' });
	assert.equal(state.items[0]?.starred, true);
	assert.equal(state.items[0]?.note, 'kept');
	assert.equal(state.items[0]?.for_revision, true);
	assert.equal(state.items[0]?.for_share, true);
	assert.equal(state.items[0]?.share_group_id, 'group-a');

	state.offset = 3;
	await state.refreshAfterRun();
	assert.match(calls.at(-1) ?? '', /offset=3/);
});
