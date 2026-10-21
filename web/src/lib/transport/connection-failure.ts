// A request the connection cut short, apart from a failure the Server answered.
//
// A Server restart (a deploy) leaves the page with three shapes of failure: the
// request cannot connect, a gateway in front answers 502, 503 or 504 with no
// detail of the Server's own, or a stream ends before its last event (seen on
// 5173 Build 1304, 2026-10-21, where a batch lost every line it sent while the
// API was down). They carry the same words as before; the kind lets a batch
// wait for the Server and send the line again instead of counting a failure.

export type ConnectionFailureKind = 'unreachable' | 'gateway' | 'cut';

export class ConnectionFailure extends Error {
	readonly kind: ConnectionFailureKind;

	constructor(kind: ConnectionFailureKind, message: string, options?: { cause?: unknown }) {
		super(message, options);
		this.name = 'ConnectionFailure';
		this.kind = kind;
	}
}

/** The statuses a gateway answers with while the Server behind it is away. */
export const GATEWAY_STATUSES: ReadonlySet<number> = new Set([502, 503, 504]);

export function isConnectionFailure(cause: unknown): cause is ConnectionFailure {
	return cause instanceof ConnectionFailure;
}

/** A request the caller stopped: never a cut connection. */
export function isAbort(cause: unknown, signal?: AbortSignal | null): boolean {
	return signal?.aborted === true || (cause instanceof Error && cause.name === 'AbortError');
}
