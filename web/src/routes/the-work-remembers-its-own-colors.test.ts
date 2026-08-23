// Run with: npm run test:unit  (node:test, no test dependency)
//
// A redraw has to say which work it is a redraw OF. The server reads that work's
// own recorded colors and draws in them, so a catalog definition that has since
// changed — 1,274 works, 46% of the corpus, measured 2026-08-09 — no longer
// repaints it silently, and one renamed or retired no longer answers 422.
//
// `catalog_id` keeps being sent beside it. It is the nameplate; only the colors
// moved. A change that dropped it would take the catalog's name off the screen
// while fixing nothing.
//
// There is no component renderer here (test:unit is node:test with no DOM), so
// the wiring is asserted in the page's own words. The control matters as much as
// the wiring: `renderColorCatalogCandidate` is the author deliberately asking for
// a DIFFERENT catalog, and sending a work reference there would pin it to the old
// colors and make the whole `Another catalog` operation a no-op.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const page = fs.readFileSync(path.join(here, '+page.svelte'), 'utf8');
const replay = fs.readFileSync(path.join(here, '../lib/features/history/replay.ts'), 'utf8');

function body(fnName: string): string {
	const start = page.indexOf(`async function ${fnName}(`);
	assert.notEqual(start, -1, `${fnName} is gone; this gate names the wrong function`);
	const next = page.indexOf('\n\tasync function ', start + 1);
	return page.slice(start, next === -1 ? page.length : next);
}

/** What the function sends: the request literal up to the response check. */
function request(fnName: string): string {
	const source = body(fnName);
	const from = source.indexOf('JSON.stringify({');
	const to = source.indexOf('if (!r.ok)');
	assert.ok(from !== -1 && to > from, `${fnName} no longer builds a request this way`);
	return source.slice(from, to);
}

test('every redraw of a saved work names the work it is redrawing', () => {
	// varyPerformance and renderWordTouchCandidate are the two touch refinements.
	// The history replay now owns its request in the history module and receives
	// only the page-built work reference and render preferences.
	for (const fn of ['varyPerformance', 'renderWordTouchCandidate']) {
		assert.match(
			request(fn),
			/workReferencePayload\(refinementWorkId\(\)\)/,
			`${fn} must send the work whose colors it is redrawing`
		);
	}
	const replayWiring = page.slice(page.indexOf('async function replayHistoryItem'), page.indexOf('function closeReplayComparison'));
	assert.match(replayWiring, /workReferencePayload\(item\.id\)/);
	assert.match(replay, /\.\.\.defaults\.renderPayload\(item, catalogId\)/);
});

test('a redraw keeps sending the catalog id as the nameplate', () => {
	// The colors stopped coming from it; the name did not. Dropping it here would
	// leave the status line with nothing to show.
	for (const fn of ['varyPerformance', 'renderWordTouchCandidate']) {
		assert.match(
			request(fn),
			/colorCatalogOverride\(refinementCatalogId\(\)\)/,
			`${fn} must still name the catalog`
		);
	}
});

test('asking for another catalog does not name a work', () => {
	// The control. `Another catalog` exists to draw the same Score in colors the
	// work was NOT drawn in, so a work reference here would pin it to the old ones
	// and every candidate would come back identical.
	assert.doesNotMatch(
		request('renderColorCatalogCandidate'),
		/work_id|workReferencePayload/,
		'renderColorCatalogCandidate must not send a work reference'
	);
	// Not vacuous: it really is a redraw of the same Score through the same endpoint.
	assert.match(request('renderColorCatalogCandidate'), /score:\s*result\.score/);
});
