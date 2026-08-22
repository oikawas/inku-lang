// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { createApiFetch, type ApiFetch } from './api-fetch.ts';

type FetchCall = {
	path: string;
	init: RequestInit | undefined;
};

function response(status: number, body = '', headers?: HeadersInit): Response {
	return new Response(body, { status, headers });
}

function sequenceFetch(responses: Response[], calls: FetchCall[]): ApiFetch {
	return async (path, init) => {
		calls.push({ path, init });
		const next = responses.shift();
		assert.ok(next, 'the transport made more requests than the test supplied');
		return next;
	};
}

test('a normal response preserves request init, clones headers, and fixes credentials', async () => {
	const calls: FetchCall[] = [];
	const expected = response(201, 'created');
	const originalHeaders = new Headers({ 'x-trace': 'trace-1' });
	const controller = new AbortController();
	const apiFetch = createApiFetch({ fetch: sequenceFetch([expected], calls) });

	const actual = await apiFetch('/api/example', {
		method: 'POST',
		body: 'payload',
		cache: 'no-store',
		headers: originalHeaders,
		signal: controller.signal,
		credentials: 'include'
	});

	assert.equal(actual, expected);
	assert.equal(calls.length, 1);
	assert.equal(calls[0].path, '/api/example');
	assert.equal(calls[0].init?.method, 'POST');
	assert.equal(calls[0].init?.body, 'payload');
	assert.equal(calls[0].init?.cache, 'no-store');
	assert.equal(calls[0].init?.signal, controller.signal);
	assert.equal(calls[0].init?.credentials, 'same-origin');
	assert.notEqual(calls[0].init?.headers, originalHeaders);
	assert.equal(new Headers(calls[0].init?.headers).get('x-trace'), 'trace-1');
	assert.equal(originalHeaders.get('x-trace'), 'trace-1');
});

test('only a capacity 503 retries, using bounded Retry-After and exponential backoff', async () => {
	const calls: FetchCall[] = [];
	const waits: Array<{ ms: number; signal: AbortSignal | null | undefined }> = [];
	const controller = new AbortController();
	const final = response(200, 'ok');
	const apiFetch = createApiFetch({
		fetch: sequenceFetch(
		[
			response(503, 'render capacity is full'),
			response(503, 'render capacity is full', { 'Retry-After': '0.05' }),
			final
		],
		calls
		),
		sleep: async (ms, signal) => {
			waits.push({ ms, signal });
		}
	});

	assert.equal(await apiFetch('/api/render', { signal: controller.signal }), final);
	assert.equal(calls.length, 3);
	assert.deepEqual(
		waits.map(({ ms }) => ms),
		[200, 50]
	);
	assert.ok(waits.every(({ signal }) => signal === controller.signal));
});

test('an unrelated 503 is returned without sleeping or retrying', async () => {
	const calls: FetchCall[] = [];
	const waits: number[] = [];
	const unavailable = response(503, 'maintenance');
	const apiFetch = createApiFetch({
		fetch: sequenceFetch([unavailable], calls),
		sleep: async (ms) => {
			waits.push(ms);
		}
	});

	assert.equal(await apiFetch('/api/render'), unavailable);
	assert.equal(calls.length, 1);
	assert.deepEqual(waits, []);
});

test('persistent capacity pressure makes at most four requests', async () => {
	const calls: FetchCall[] = [];
	const waits: number[] = [];
	const exhausted = Array.from({ length: 4 }, () => response(503, 'render capacity is full'));
	const final = exhausted[3];
	const apiFetch = createApiFetch({
		fetch: sequenceFetch(exhausted, calls),
		sleep: async (ms) => {
			waits.push(ms);
		}
	});

	assert.equal(await apiFetch('/api/render'), final);
	assert.equal(calls.length, 4);
	assert.deepEqual(waits, [200, 400, 800]);
});

test('invalid, zero, and negative Retry-After values use the normal backoff', async () => {
	for (const retryAfter of ['invalid', '0', '-2']) {
		const waits: number[] = [];
		const apiFetch = createApiFetch({
			fetch: sequenceFetch(
				[
					response(503, 'render capacity is full', { 'Retry-After': retryAfter }),
					response(200)
				],
				[]
			),
			sleep: async (ms) => {
				waits.push(ms);
			}
		});

		await apiFetch('/api/render');
		assert.deepEqual(waits, [200], `Retry-After: ${retryAfter}`);
	}
});

test('an abort during the default wait rejects with AbortError', async () => {
	const controller = new AbortController();
	const calls: FetchCall[] = [];
	const apiFetch = createApiFetch({
		fetch: sequenceFetch([response(503, 'render capacity is full')], calls)
	});
	const pending = apiFetch('/api/render', { signal: controller.signal });
	queueMicrotask(() => controller.abort());

	await assert.rejects(pending, (error: unknown) => {
		return error instanceof DOMException && error.name === 'AbortError';
	});
	assert.equal(calls.length, 1);
	assert.equal(calls[0].init?.signal, controller.signal);
});
