// The signal that ends a proxied API request once its reader has gone.
//
// `hooks.server.ts` forwards /api/* to the API with `fetch`. A reader that
// stops (the model comparison's stop, a closed page) must reach the API, or
// the run it asked for goes on through every model retry: the API cancels a
// run whose request has gone, but only a closed upstream connection tells it
// so. SvelteKit's request signal aborts only while the request body is still
// arriving, so a short JSON body sent in full and then abandoned never
// aborted anything. The browser's connection closing is the sign that holds.

/** The part of Node's request this watches: its connection closing. */
export type NodeRequest = {
	socket?: {
		once(event: 'close', listener: () => void): unknown;
		off(event: 'close', listener: () => void): unknown;
	};
};

export type ReaderSignal = {
	signal: AbortSignal;
	/** Stop watching once the response has been read, so a kept-alive connection gathers no listeners. */
	release: () => void;
};

export function readerSignal(requestSignal: AbortSignal, req: NodeRequest | undefined): ReaderSignal {
	const controller = new AbortController();
	const abort = () => controller.abort();
	const socket = req?.socket;
	socket?.once('close', abort);
	requestSignal.addEventListener('abort', abort, { once: true });
	return {
		signal: controller.signal,
		release: () => {
			socket?.off('close', abort);
			requestSignal.removeEventListener('abort', abort);
		}
	};
}
