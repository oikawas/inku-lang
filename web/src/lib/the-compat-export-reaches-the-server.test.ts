import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const download = readFileSync(new URL('./features/export/download.ts', import.meta.url), 'utf8');

test('T-326 compat export keeps the selected server profile on its one web path', () => {
	// Only a saved work is exported since 2026-09-27, so the unsaved path that
	// sent the Score to /api/render-svg is gone and the profile reaches the
	// server through the work's own route.
	const body = download.slice(download.indexOf('async function downloadSVG'));
	assert.match(body, /\/api\/history\/\$\{displayedHistoryItem\.id\}\/svg\?profile=\$\{profile\}/);
	assert.doesNotMatch(body, /\/api\/render-svg/);
});
