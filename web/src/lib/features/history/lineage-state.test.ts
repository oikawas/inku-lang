import assert from 'node:assert/strict';
import { test } from 'node:test';

import type { LineageGraph } from './types.ts';

const identity = <T>(value: T): T => value;
const stateShim = identity as (<T>(value: T) => T) & { raw: <T>(value: T) => T };
stateShim.raw = identity;
(globalThis as unknown as Record<string, unknown>).$state = stateShim;

const { LineageQueryState } = await import('./lineage-state.svelte.ts');

type PendingRequest = {
	path: string;
	init?: RequestInit;
	resolve: (response: Response) => void;
};

function deferredTransport() {
	const requests: PendingRequest[] = [];
	const apiFetch = (path: string, init?: RequestInit): Promise<Response> => new Promise((resolve) => {
		requests.push({ path, init, resolve });
	});
	return { apiFetch, requests };
}

function jsonResponse(value: unknown, status = 200): Response {
	return new Response(JSON.stringify(value), {
		status,
		headers: { 'Content-Type': 'application/json' }
	});
}

function graph(focus: string, nodes = [focus], edges: LineageGraph['edges'] = []): LineageGraph {
	return {
		focus_node_id: focus,
		nodes: nodes.map((id) => ({ id, state: 'active', at: 1, history: null })),
		edges
	};
}

test('T-267/T-268: the latest base lineage request alone may settle state', async () => {
	const { apiFetch, requests } = deferredTransport();
	const state = new LineageQueryState(apiFetch);

	const first = state.load('node-a');
	const second = state.load('node-b');
	assert.equal(state.loading, true);
	assert.equal(requests[0]?.path, '/api/lineage/node-a?descendant_depth=3&node_limit=200');
	assert.equal(requests[0]?.init?.cache, 'no-store');
	assert.equal(requests[1]?.path, '/api/lineage/node-b?descendant_depth=3&node_limit=200');

	requests[1]?.resolve(jsonResponse(graph('node-b')));
	await second;
	requests[0]?.resolve(jsonResponse(graph('node-a')));
	await first;

	assert.equal(state.graph?.focus_node_id, 'node-b');
	assert.equal(state.loading, false);
	assert.equal(state.error, null);

	await state.load('node-b');
	assert.equal(requests.length, 2, 'the loaded focus is not fetched twice');
	const forced = state.load('node-b', true);
	assert.equal(requests.length, 3);
	requests[2]?.resolve(jsonResponse(graph('node-b')));
	await forced;

	const failed = state.load('node-c');
	requests[3]?.resolve(jsonResponse({}, 503));
	await failed;
	assert.equal(state.graph?.focus_node_id, 'node-b');
	assert.equal(state.error, 'HTTP 503');
	assert.equal(state.loading, false);
});

test('T-268: reset invalidates a response already in flight', async () => {
	const { apiFetch, requests } = deferredTransport();
	const state = new LineageQueryState(apiFetch);

	const pending = state.load('node-a');
	state.reset();
	requests[0]?.resolve(jsonResponse(graph('node-a')));
	await pending;

	assert.equal(state.graph, null);
	assert.equal(state.loading, false);
	assert.equal(state.error, null);
});

test('T-269: a branch merges by id only while the same focus is current', async () => {
	const { apiFetch, requests } = deferredTransport();
	const state = new LineageQueryState(apiFetch);
	state.graph = graph('focus', ['focus', 'existing'], [
		{ id: 'edge-existing', parent_node_id: 'focus', child_node_id: 'existing', derivation_kind: 'replay' }
	]);

	const merge = state.loadBranch('existing');
	assert.equal(requests[0]?.path, '/api/lineage/existing?descendant_depth=1&node_limit=200');
	requests[0]?.resolve(jsonResponse(graph('existing', ['existing', 'child'], [
		{ id: 'edge-child', parent_node_id: 'existing', child_node_id: 'child', derivation_kind: 'variation' }
	])));
	await merge;

	assert.deepEqual(state.graph?.nodes.map((node) => node.id), ['focus', 'existing', 'child']);
	assert.deepEqual(state.graph?.edges.map((edge) => edge.id), ['edge-existing', 'edge-child']);
	assert.equal(state.graph?.focus_node_id, 'focus');

	const stale = state.loadBranch('child');
	state.graph = graph('other');
	requests[1]?.resolve(jsonResponse(graph('child', ['child', 'late'])));
	await stale;
	assert.equal(state.graph?.focus_node_id, 'other');
	assert.deepEqual(state.graph?.nodes.map((node) => node.id), ['other']);
});

test('T-270: overview starts at the loaded root and keeps the selected focus', async () => {
	const { apiFetch, requests } = deferredTransport();
	const state = new LineageQueryState(apiFetch);
	state.graph = graph('focus', ['root', 'focus'], [
		{ id: 'root-focus', parent_node_id: 'root', child_node_id: 'focus', derivation_kind: 'replay' }
	]);

	const pending = state.loadOverview('fallback');
	assert.equal(requests[0]?.path, '/api/lineage/root?descendant_depth=200&node_limit=200');
	requests[0]?.resolve(jsonResponse(graph('root', ['root', 'focus', 'descendant'])));
	await pending;

	assert.equal(state.graph?.focus_node_id, 'focus');
	assert.deepEqual(state.graph?.nodes.map((node) => node.id), ['root', 'focus', 'descendant']);

	const stale = state.loadOverview(null);
	const replacement = state.load('replacement', true);
	requests[2]?.resolve(jsonResponse(graph('replacement')));
	await replacement;
	requests[1]?.resolve(jsonResponse(graph('root', ['root', 'late'])));
	await stale;
	assert.equal(state.graph?.focus_node_id, 'replacement');
	assert.deepEqual(state.graph?.nodes.map((node) => node.id), ['replacement']);
});

test('T-271: nearby work deduplicates ids, clears first, and drops late answers', async () => {
	const { apiFetch, requests } = deferredTransport();
	const state = new LineageQueryState(apiFetch);

	const first = state.loadNearby('history-a');
	assert.deepEqual(state.nearby, []);
	const second = state.loadNearby('history-b');
	assert.equal(requests[0]?.path, '/api/history/history-a/neighbors');
	assert.equal(requests[0]?.init?.cache, 'no-store');
	assert.equal(requests[1]?.path, '/api/history/history-b/neighbors');

	requests[1]?.resolve(jsonResponse([{ id: 'near-b', input: 'b', svg: '<svg/>' }]));
	await second;
	requests[0]?.resolve(jsonResponse([{ id: 'near-a', input: 'a', svg: '<svg/>' }]));
	await first;
	assert.deepEqual(state.nearby.map((item) => item.id), ['near-b']);

	await state.loadNearby('history-b');
	assert.equal(requests.length, 2);
	await state.loadNearby(null);
	assert.deepEqual(state.nearby, []);
	assert.equal(requests.length, 2);

	const failed = state.loadNearby('history-c');
	requests[2]?.resolve(jsonResponse({}, 503));
	await failed;
	assert.deepEqual(state.nearby, []);
});

test('T-272: named history projections update only the matching lineage node', () => {
	const state = new LineageQueryState(async () => jsonResponse({}));
	state.graph = {
		focus_node_id: 'node-a',
		nodes: [
			{
				id: 'node-a',
				state: 'active',
				at: 1,
				history: {
					id: 'history-a',
					input: 'a',
					ddl: null,
					score: { instructions: [] },
					svg: '',
					at: 1,
					starred: false,
					for_revision: false,
					for_share: false
				}
			},
			{ id: 'node-b', state: 'active', at: 2, history: null }
		],
		edges: []
	};

	state.applyStarState({ id: 'history-a', starred: true, note: 'kept' });
	state.applyForRevisionState({ id: 'history-a', for_revision: true });
	state.applyForShareState({ id: 'history-a', for_share: true, share_group_id: 'group-a' });

	const history = state.graph?.nodes[0]?.history;
	assert.equal(history?.starred, true);
	assert.equal(history?.note, 'kept');
	assert.equal(history?.for_revision, true);
	assert.equal(history?.for_share, true);
	assert.equal(history?.share_group_id, 'group-a');
	assert.equal(state.graph?.nodes[1]?.history, null);
});
