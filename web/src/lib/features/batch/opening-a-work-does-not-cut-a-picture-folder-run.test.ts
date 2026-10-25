import assert from 'node:assert/strict';
import { existsSync } from 'node:fs';
import { registerHooks } from 'node:module';
import { test } from 'node:test';

import type { WorkStateDeps } from '../work/state.svelte.ts';

// 2026-10-25: a folder of five pictures saved three. Opening a saved work while
// the fourth ran moved the shared pipeline controller's request ordinal; its run
// returned at score_ready without performing, the batch counted it painted, and
// the fifth went the same way. Nothing said so.

const libRoot = new URL('../../', import.meta.url);
registerHooks({
	resolve(specifier, context, nextResolve) {
		if (specifier.startsWith('$lib/')) {
			const file = new URL(`${specifier.slice(5)}.ts`, libRoot);
			const target = existsSync(file) ? file : new URL(`${specifier.slice(5)}/index.ts`, libRoot);
			return nextResolve(target.href, context);
		}
		return nextResolve(specifier, context);
	}
});
const identity = <T>(value: T): T => value;
const runeHost = globalThis as unknown as Record<string, unknown>;
runeHost.$state = Object.assign(identity, { raw: identity });
runeHost.$derived = Object.assign(identity, { by: <T>(read: () => T): T => read() });

const { createWorkState } = await import('../work/state.svelte.ts');

type Work = ReturnType<typeof createWorkState>;

function json(body: unknown, status = 200): Response {
	return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } });
}

function view(n: number, tag: string, extra: Record<string, unknown> = {}) {
	return {
		execution_id: `e${n}`, variation_id: `v${n}`, authority: {}, description: '', document: null,
		phase: { tag }, delivery: null, busy: false, rendered: null, result: null, image_provenance: `p${n}`,
		...extra,
	};
}

/**
 * A Server that runs each picture through busy -> score_ready, then saves it on
 * perform. `onLoad` runs once, on the first poll of the first picture.
 */
function pictureServer(onFirstPoll: () => void) {
	let started = 0;
	let firstPoll = true;
	const polls = new Map<string, number>();
	const performed: string[] = [];
	const fetch = async (path: string, init?: RequestInit): Promise<Response> => {
		const method = init?.method ?? 'GET';
		if (path === '/api/pipeline/images' && method === 'POST') {
			return json({ image_id: `i${started + 1}`, thumbnail: '', original_width: 10, original_height: 10, width: 10, height: 10, nearest_format_id: 'square' });
		}
		if (path === '/api/pipeline/variations' && method === 'POST') {
			started += 1;
			return json(view(started, 'awaiting_llm', { busy: true }));
		}
		const load = path.match(/^\/api\/pipeline\/variations\/v(\d+)$/);
		if (load) {
			const n = Number(load[1]);
			if (firstPoll) { firstPoll = false; onFirstPoll(); }
			const count = (polls.get(`v${n}`) ?? 0) + 1;
			polls.set(`v${n}`, count);
			return json(count < 2 ? view(n, 'awaiting_llm', { busy: true }) : view(n, 'score_ready', { delivery: { score: {} } }));
		}
		const command = path.match(/^\/api\/pipeline\/executions\/e(\d+)\/commands$/);
		if (command) {
			const n = Number(command[1]);
			performed.push(`v${n}`);
			return json(view(n, 'completed', { delivery: { score: {} }, result: { history_id: `h${n}` } }));
		}
		throw new Error(`unexpected request ${method} ${path}`);
	};
	return { fetch, performed, started: () => started };
}

function pictureWork(fetch: (path: string, init?: RequestInit) => Promise<Response>) {
	let refreshed = 0;
	const work = createWorkState({
		apiFetch: fetch,
		batch: { resuming: false, running: false }, demo: { running: false, updateLiveTime: () => {} },
		refinementSession: { gridBusy: false }, session: {},
		describeApiError: (detail: unknown) => JSON.stringify(detail),
		history: () => ({ clearSelection: () => {}, items: [], fetchOffset: async () => true,
			refreshAfterServerSave: async () => { refreshed += 1; } }),
		canvasViewport: { fit: () => {} }, canvasAspectId: () => 'square',
		resetTargetScopedState: () => {}, showCanvas: () => {}, requestConfirmation: () => {},
		models: { stage1Provider: () => 'openai', stage1Model: () => 'm', stage2Provider: () => 'openai',
			stage2Model: () => 'm', visionProvider: () => 'openai', visionModel: () => 'v',
			includeThinking: () => false, available: () => [] },
	} as unknown as WorkStateDeps);
	return { work, refreshed: () => refreshed };
}

async function finished(work: Work): Promise<void> {
	for (let i = 0; i < 200 && work.imageFolder.running; i += 1) await new Promise((resolve) => setTimeout(resolve, 25));
	assert.equal(work.imageFolder.running, false, 'the batch did not finish');
}

test('opening a saved work while a picture runs does not cut that picture short', async () => {
	let work!: Work;
	const server = pictureServer(() => { void work.selectHistoryAuthority('opened-work', 'opened-variation'); });
	const made = pictureWork(server.fetch);
	work = made.work;
	work.imageFolder.pick([new File([new Uint8Array(4)], '1.jpg'), new File([new Uint8Array(4)], '2.jpg')]);
	work.runImageFolder(true);
	await finished(work);
	assert.deepEqual(server.performed, ['v1', 'v2'], 'each picture is performed, so it is saved');
	assert.equal(work.imageFolder.success, 2);
	assert.equal(work.imageFolder.failures.length, 0);
	assert.equal(made.refreshed(), 2, 'the history list learns of each saved work');
});

test('a picture whose run ends without a saved work is a failure, not a success', async () => {
	const fetch = async (path: string, init?: RequestInit): Promise<Response> => {
		if (path === '/api/pipeline/images') return json({ image_id: 'i1', thumbnail: '', original_width: 1, original_height: 1, width: 1, height: 1, nearest_format_id: 'square' });
		if (path === '/api/pipeline/variations' && init?.method === 'POST') return json(view(1, 'awaiting_patch_approval'));
		throw new Error(`unexpected request ${path}`);
	};
	const { work } = pictureWork(fetch);
	work.imageFolder.pick([new File([new Uint8Array(4)], '1.jpg')]);
	work.runImageFolder(true);
	await finished(work);
	assert.equal(work.imageFolder.success, 0);
	assert.equal(work.imageFolder.pending.length, 1, 'Continue paints it again');
});
