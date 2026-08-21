import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const download = readFileSync(new URL('./features/export/download.ts', import.meta.url), 'utf8');

test('T-326 compat export keeps the selected server profile on both web paths', () => {
	const body = download.slice(download.indexOf('async function downloadSVG'));
	assert.match(body, /\/api\/history\/\$\{displayedHistoryItem\.id\}\/svg\?profile=\$\{profile\}/);
	assert.match(body, /svg_profile: profile/);
});
