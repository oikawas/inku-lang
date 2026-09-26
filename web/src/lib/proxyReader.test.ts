// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { EventEmitter } from 'node:events';
import { test } from 'node:test';

import { readerSignal, type NodeRequest } from './proxyReader.ts';

test('a reader whose connection closes aborts the upstream request, until released', () => {
	// A stopped model comparison left its API request, and the run behind it,
	// going: the body had arrived in full, so SvelteKit's signal never aborted.
	const socket = new EventEmitter();
	const req = { socket } as NodeRequest;
	const left = readerSignal(new AbortController().signal, req);
	socket.emit('close');
	assert.equal(left.signal.aborted, true);

	const read = readerSignal(new AbortController().signal, req);
	read.release();
	assert.equal(socket.listenerCount('close'), 0);
	socket.emit('close');
	assert.equal(read.signal.aborted, false);
});
