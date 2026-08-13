// Run with: npm run test:unit  (node:test, no test dependency)
//
// [I-157], the web half. Both of these send a Score back to /api/render-svg to
// be drawn again, and neither sent the full pair of seeds, so what came back
// was another performance of the same score.
//
// The narrow claim, from the ruling (author, 2026-08-13, option A): a redraw is
// not promised to equal the saved picture -- principle 7 says the engine only
// moves forward and the past version is not kept -- but what separates the two
// must be the engine having moved on, and nothing else.
//
// The replay screen is where that bites hardest. It draws the saved work beside
// a fresh one and captions the pair with which engine version each came from.
// A dropped placement seed moved the marks, and that motion was read as the
// engine's: the one thing this screen exists to measure.
//
// Both callers send the raw fields rather than `composition_seed ?? render_seed`
// -- renderer.py:3486 already falls back to the performance seed when a work
// carries no composition seed, and a copy of that rule in four clients is four
// places for it to drift.
//
// T-56 (the replay sends the placement seed), T-57 (the export sends both).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const PAGE = read('../routes/+page.svelte');
const DOWNLOAD = read('./features/export/download.ts');

/** The body of the /api/render-svg call inside replayHistoryItem. */
const REPLAY = (() => {
	const start = PAGE.indexOf('async function replayHistoryItem');
	assert.notEqual(start, -1, 'replayHistoryItem is gone');
	const body = PAGE.slice(start);
	return body.slice(0, body.indexOf('const r = await r'));
})();

// ------------------------------------------------------------------- T-56

test('T-56  the replay sends the seed that places the marks', () => {
	// Both, not one: sending only the performance seed is what made the marks
	// move, because the renderer then places them from it.
	assert.match(REPLAY, /render_seed: replaySeed,/);
	assert.match(REPLAY, /composition_seed: it\.composition_seed \?\? null,/);
});

test('T-56  it reads the placement seed off the work, not off the screen', () => {
	// `it` is the history item being replayed. Reading the seed from the work
	// currently drawn would replay every item with the same placement.
	const line = REPLAY.match(/composition_seed: ([^,]+),/);
	assert.ok(line, 'the replay sends no composition seed');
	assert.match(line[1], /^it\./);
});

// ------------------------------------------------------------------- T-57

test('T-57  the export sends both seeds', () => {
	const body = DOWNLOAD.slice(DOWNLOAD.indexOf("'/api/render-svg'"));
	const call = body.slice(0, body.indexOf('})'));
	assert.match(call, /render_seed: result\.render_seed \?\? null/);
	assert.match(call, /composition_seed: result\.composition_seed \?\? null/);
	// Which the deps type has to allow, or the two lines above are `undefined`
	// with the compiler none the wiser.
	assert.match(DOWNLOAD, /render_seed\?: number \| null;/);
	assert.match(DOWNLOAD, /composition_seed\?: number \| null;/);
});

test('T-57  the display profile is still the stored picture', () => {
	// The redraw is the other branch. `display` takes the SVG already in hand
	// and only stamps the description into it -- the stored print is the work.
	const svgExport = DOWNLOAD.slice(DOWNLOAD.indexOf('async function downloadSVG'));
	const branch = svgExport.slice(
		svgExport.indexOf("if (profile === 'display')"),
		svgExport.indexOf('} else if')
	);
	assert.ok(branch.length > 0, 'the display branch is gone');
	assert.match(branch, /result\.svg\.replace/);
	assert.doesNotMatch(branch, /apiFetch/);
});
