// Run with: npm run test:unit  (node:test, no test dependency)
import assert from 'node:assert/strict';
import { test } from 'node:test';

import { startupAnswer } from './startup.ts';

test('only the server saying so means signed out; an unreachable server is waited for', () => {
	// An API restarting behind the web proxy (502) showed the sign-in form,
	// even to a single-user install.
	assert.equal(startupAnswer(200), 'signed-in');
	assert.equal(startupAnswer(401), 'signed-out');
	assert.equal(startupAnswer(403), 'signed-out');
	assert.equal(startupAnswer(502), 'unreachable');
	assert.equal(startupAnswer(500), 'unreachable');
	assert.equal(startupAnswer(null), 'unreachable');
});
