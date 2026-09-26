import { env } from '$env/dynamic/private';
import type { Handle } from '@sveltejs/kit';

import { headersForDecodedBody } from '$lib/proxyResponse';
import { readerSignal, type NodeRequest } from '$lib/proxyReader';

const apiBaseUrl = (env.INKU_API_BASE_URL ?? '').replace(/\/+$/, '');

export const handle: Handle = async ({ event, resolve }) => {
	if (apiBaseUrl && event.url.pathname.startsWith('/api/')) {
		const target = new URL(event.url.pathname + event.url.search, apiBaseUrl);
		const headers = new Headers(event.request.headers);
		headers.delete('host');
		headers.set('x-forwarded-host', event.url.host);
		headers.set('x-forwarded-proto', event.url.protocol.slice(0, -1));
		// adapter-node hands over the Node request; without it (vite dev) only
		// SvelteKit's own request signal is watched.
		const reader = readerSignal(event.request.signal, (event.platform as { req?: NodeRequest } | undefined)?.req);
		let upstream: Response;
		try {
			upstream = await fetch(target, {
				method: event.request.method,
				headers,
				body: event.request.method === 'GET' || event.request.method === 'HEAD'
					? undefined
					: event.request.body,
				duplex: 'half',
				signal: reader.signal
			} as RequestInit);
		} catch (error) {
			reader.release();
			// Nobody is left to read an answer.
			if (reader.signal.aborted) return new Response(null, { status: 499 });
			throw error;
		}
		const body = upstream.body?.pipeThrough(new TransformStream({ flush: reader.release })) ?? null;
		if (!body) reader.release();
		return new Response(body, {
			status: upstream.status,
			statusText: upstream.statusText,
			headers: headersForDecodedBody(upstream.headers)
		});
	}

	const response = await resolve(event);
	response.headers.set('x-content-type-options', 'nosniff');
	response.headers.set('referrer-policy', 'same-origin');
	response.headers.set('x-frame-options', 'DENY');
	return response;
};
