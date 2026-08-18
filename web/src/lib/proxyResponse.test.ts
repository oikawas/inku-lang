// Run with: npm run test:unit  (node:test, no test dependency)
//
// The published image answered every gzipped API response with a body the
// browser could not read: fetch had already decoded it, and the proxy handed
// back the upstream `content-encoding: gzip` anyway. The page showed
// `TypeError: Failed to fetch` on a 200, and login died on `r.json()` before it
// could load anything (measured 2026-08-18 against v2.13.41).
//
// T-298 (the encoding headers do not survive), T-299 (everything else does),
// T-300 (the proxy actually goes through it).
//
// ⚠ The failure itself cannot be reproduced here: gunzipping is the browser's
// network layer, and node's Response does not decode a body at all. So these
// measure the two things that are measurable off the wire -- that the labels
// are dropped, and that the one caller uses the function -- and the wire itself
// is checked against the published image after a release.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { HEADERS_DESCRIBING_THE_ENCODED_BODY, headersForDecodedBody } from './proxyResponse.ts';

const HOOKS = readFileSync(new URL('../hooks.server.ts', import.meta.url), 'utf8');

test('T-298  a decoded body keeps neither the encoding nor the encoded length', () => {
	const upstream = new Headers({
		'content-encoding': 'gzip',
		'content-length': '489',
		'content-type': 'application/json'
	});

	const headers = headersForDecodedBody(upstream);

	assert.equal(headers.get('content-encoding'), null);
	assert.equal(headers.get('content-length'), null);
	// Both names are what the upstream actually sends; a list that lost one of
	// them would leave the browser gunzipping plain text again.
	assert.deepEqual([...HEADERS_DESCRIBING_THE_ENCODED_BODY], ['content-encoding', 'content-length']);
});

test('T-299  every other header the API sent is still there', () => {
	const upstream = new Headers({
		'content-encoding': 'gzip',
		'content-type': 'application/json',
		vary: 'Accept-Encoding',
		'set-cookie': 'inku_session=abc; Path=/; HttpOnly'
	});

	const headers = headersForDecodedBody(upstream);

	assert.equal(headers.get('content-type'), 'application/json');
	assert.equal(headers.get('vary'), 'Accept-Encoding');
	assert.equal(headers.get('set-cookie'), 'inku_session=abc; Path=/; HttpOnly');
	// The upstream headers must not be mutated: the caller may still read them.
	assert.equal(upstream.get('content-encoding'), 'gzip');
});

test('T-300  the proxy builds its response through it, not from the upstream headers', () => {
	assert.ok(
		HOOKS.includes('headersForDecodedBody(upstream.headers)'),
		'hooks.server.ts must pass the upstream headers through headersForDecodedBody'
	);
	assert.ok(
		!/headers:\s*upstream\.headers/.test(HOOKS),
		'hooks.server.ts must not hand the upstream headers straight back'
	);
});
