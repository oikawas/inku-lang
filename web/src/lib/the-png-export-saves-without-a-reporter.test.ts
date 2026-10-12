// Run with: npm run test:unit  (node:test, no test dependency)
//
// PNG from the canvas's export menu did nothing (author, 2026-10-12). The save
// was written as the argument of the optional reporter:
//
//     deps.onSaved?.(await triggerDownload(...))
//
// When `onSaved` is absent the optional call skips its arguments, so the file
// was never handed to the browser. The saved-work menu passes no reporter.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const DOWNLOAD = readFileSync(new URL('./features/export/download.ts', import.meta.url), 'utf8');

test('no save is made inside the argument list of an optional call', () => {
	const calls = DOWNLOAD.match(/\?\.\([^;]*\btriggerDownload\(/g) ?? [];
	assert.deepEqual(calls, []);
});

test('the PNG export saves as a statement of its own', () => {
	const png = DOWNLOAD.slice(DOWNLOAD.indexOf('async function downloadPNG'));
	assert.match(png, /\n\t\tconst outcome = await triggerDownload\(stamped, /);
});
