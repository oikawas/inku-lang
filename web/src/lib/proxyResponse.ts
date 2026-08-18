// Headers for a body the runtime already decoded.
//
// `hooks.server.ts` forwards /api/* to the API with `fetch`, and fetch decodes a
// compressed upstream body before the handler ever sees it. Passing the upstream
// headers straight back therefore ships `content-encoding: gzip` (and the
// compressed `content-length`) attached to plain bytes: the browser tries to
// gunzip text, the read fails, and the page reports `TypeError: Failed to fetch`
// on a response whose status was 200. Measured 2026-08-18 against the published
// image -- /api/info (below the gzip threshold) read fine while /api/auth/me and
// /api/plugins did not, and curl said `incorrect header check`.
//
// Both headers have to go: content-encoding because the body is no longer
// encoded, content-length because the decoded body is a different size.
export const HEADERS_DESCRIBING_THE_ENCODED_BODY = ['content-encoding', 'content-length'] as const;

export function headersForDecodedBody(upstream: Headers): Headers {
	const headers = new Headers(upstream);
	for (const name of HEADERS_DESCRIBING_THE_ENCODED_BODY) headers.delete(name);
	return headers;
}
