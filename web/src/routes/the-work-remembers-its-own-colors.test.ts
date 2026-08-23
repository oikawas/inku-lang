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
// the page wiring and canonical redraw action are both asserted. The control
// matters as much as the wiring: `renderColorCatalogCandidate` deliberately asks for
// a DIFFERENT catalog, and sending a work reference there would pin it to the old
// colors and make the whole `Another catalog` operation a no-op.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const page = fs.readFileSync(path.join(here, '+page.svelte'), 'utf8');
const redraw = fs.readFileSync(path.join(here, '../lib/features/canvas/refinement-redraw.ts'), 'utf8');
const replay = fs.readFileSync(path.join(here, '../lib/features/history/replay.ts'), 'utf8');

function body(source: string, fnName: string): string {
	const start = source.indexOf(`function ${fnName}(`);
	assert.notEqual(start, -1, `${fnName} is gone; this gate names the wrong function`);
	const markers = source === page ? ['\n\tasync function ', '\n\tfunction '] : ['\nexport '];
	const next = markers
		.map((marker) => source.indexOf(marker, start + 1))
		.filter((index) => index !== -1)
		.sort((left, right) => left - right)[0] ?? -1;
	return source.slice(start, next === -1 ? source.length : next);
}

/** What the function sends: the request literal up to the response check. */
function request(sourceText: string, fnName: string): string {
	const source = body(sourceText, fnName);
	const from = source.indexOf('JSON.stringify({');
	const to = source.indexOf('if (!', from);
	assert.ok(from !== -1 && to > from, `${fnName} no longer builds a request this way`);
	return source.slice(from, to);
}

test('every redraw of a saved work names the work it is redrawing', () => {
	// The page passes the work reference to the single action, while the word-touch
	// candidate still builds its request at the route transport boundary.
	// The history replay now owns its request in the history module and receives
	// only the page-built work reference and render preferences.
	assert.match(body(page, 'varyPerformance'), /workReference:\s*workReferencePayload\(refinementWorkId\(\)\)/);
	assert.match(request(redraw, 'runTouchRedraw'), /\.\.\.input\.workReference/);
	assert.match(request(page, 'renderWordTouchCandidate'), /workReferencePayload\(refinementWorkId\(\)\)/);
	const replayWiring = page.slice(page.indexOf('async function replayHistoryItem'), page.indexOf('function closeReplayComparison'));
	assert.match(replayWiring, /workReferencePayload\(item\.id\)/);
	assert.match(replay, /\.\.\.defaults\.renderPayload\(item, catalogId\)/);
});

test('a redraw keeps sending the catalog id as the nameplate', () => {
	// The colors stopped coming from it; the name did not. Dropping it here would
	// leave the status line with nothing to show.
	assert.match(body(page, 'varyPerformance'), /renderPayload:\s*renderSettingsPayload\('render-svg', colorCatalogOverride\(refinementCatalogId\(\)\)\)/);
	assert.match(request(redraw, 'runTouchRedraw'), /\.\.\.input\.renderPayload/);
	assert.match(request(page, 'renderWordTouchCandidate'), /colorCatalogOverride\(refinementCatalogId\(\)\)/);
});

test('asking for another catalog does not name a work', () => {
	// The control. `Another catalog` exists to draw the same Score in colors the
	// work was NOT drawn in, so a work reference here would pin it to the old ones
	// and every candidate would come back identical.
	assert.doesNotMatch(
		request(page, 'renderColorCatalogCandidate'),
		/work_id|workReferencePayload/,
		'renderColorCatalogCandidate must not send a work reference'
	);
	// Not vacuous: it really is a redraw of the same Score through the same endpoint.
	assert.match(request(page, 'renderColorCatalogCandidate'), /score:\s*result\.score/);
});
