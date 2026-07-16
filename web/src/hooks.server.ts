import { env } from '$env/dynamic/private';
import type { Handle } from '@sveltejs/kit';

const apiBaseUrl = (env.INKU_API_BASE_URL ?? '').replace(/\/+$/, '');

export const handle: Handle = async ({ event, resolve }) => {
	if (apiBaseUrl && event.url.pathname.startsWith('/api/')) {
		const target = new URL(event.url.pathname + event.url.search, apiBaseUrl);
		const headers = new Headers(event.request.headers);
		headers.delete('host');
		headers.set('x-forwarded-host', event.url.host);
		headers.set('x-forwarded-proto', event.url.protocol.slice(0, -1));
		const upstream = await fetch(target, {
			method: event.request.method,
			headers,
			body: event.request.method === 'GET' || event.request.method === 'HEAD'
				? undefined
				: event.request.body,
			duplex: 'half'
		} as RequestInit);
		return new Response(upstream.body, {
			status: upstream.status,
			statusText: upstream.statusText,
			headers: upstream.headers
		});
	}

	const response = await resolve(event);
	response.headers.set('x-content-type-options', 'nosniff');
	response.headers.set('referrer-policy', 'same-origin');
	response.headers.set('x-frame-options', 'DENY');
	return response;
};
