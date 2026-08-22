export type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

type Sleep = (ms: number, signal?: AbortSignal | null) => Promise<void>;

type ApiFetchDependencies = Readonly<{
	fetch: ApiFetch;
	sleep: Sleep;
}>;

const RENDER_CAPACITY_RETRIES = 3;

function abortError(): DOMException {
	return new DOMException('Aborted', 'AbortError');
}

function delay(ms: number, signal?: AbortSignal | null): Promise<void> {
	return new Promise((resolve, reject) => {
		if (signal?.aborted) {
			reject(abortError());
			return;
		}

		const timer = globalThis.setTimeout(() => {
			signal?.removeEventListener('abort', onAbort);
			resolve();
		}, ms);
		function onAbort() {
			globalThis.clearTimeout(timer);
			reject(abortError());
		}
		signal?.addEventListener('abort', onAbort, { once: true });
	});
}

export function createApiFetch(
	dependencies: Partial<ApiFetchDependencies> = {}
): ApiFetch {
	const fetchRequest = dependencies.fetch ?? ((path, init) => globalThis.fetch(path, init));
	const sleep = dependencies.sleep ?? delay;

	return async (path: string, init: RequestInit = {}): Promise<Response> => {
		const headers = new Headers(init.headers);
		for (let attempt = 0; ; attempt += 1) {
			const response = await fetchRequest(path, {
				...init,
				headers,
				credentials: 'same-origin'
			});

			// The server holds a fixed number of render slots and refuses immediately
			// (no queueing) when they are all taken, so a fan-out such as the 4-candidate
			// grid can lose requests to a 503 that a short wait would have avoided.
			// Retry that one condition here; every other status is passed through.
			if (response.status !== 503 || attempt >= RENDER_CAPACITY_RETRIES) return response;
			const body = await response.clone().text().catch(() => '');
			if (!body.includes('render capacity is full')) return response;

			// Slots free in well under the Retry-After of 1s the server suggests,
			// so back off in shorter steps but never longer than it asked for.
			const retryAfterMs = Number(response.headers.get('Retry-After')) * 1000;
			const backoffMs = 200 * 2 ** attempt;
			await sleep(
				Number.isFinite(retryAfterMs) && retryAfterMs > 0
					? Math.min(retryAfterMs, backoffMs)
					: backoffMs,
				init.signal
			);
		}
	};
}
