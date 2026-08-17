// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-203, ledger I-191. Four different places on this page build a history
// request, and every one of them has to carry the share filter or the reader
// gets a listing that disagrees with the button they just pressed.
//
// The number is the point. Three of the four were found by searching for the
// existing filters and fixing what turned up; the fourth -- the strip's own
// fetch -- is in a different file and was missed by exactly that method when
// the ledger entry for I-191 was written (it said "three places"; the measured
// count is four). So this counts the sites rather than checking a handful by
// name: a test that named three would be green with the fourth still missing,
// which is the failure it exists to catch.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');

/** Every file that builds a history request, and what it is. */
const SOURCES = [
	{ name: 'historyManagerState.svelte.ts', source: read('./historyManagerState.svelte.ts') },
	{ name: 'components/HistoryManager.svelte', source: read('./components/HistoryManager.svelte') },
	{ name: 'routes/+page.svelte', source: read('../routes/+page.svelte') }
] as const;

/** `params.set('<key>', ...)` occurrences in one source. */
const setsOf = (source: string, key: string) =>
	source.match(new RegExp(`params\\.set\\('${key}',`, 'g')) ?? [];

test('T-203  every place that asks for a filtered listing asks for the share bundle', () => {
	// The revision mark is the control: it is the most recently added of the two
	// filters that already worked, so wherever it is written is where a listing
	// request is built. If this count ever moves, a fifth site appeared and the
	// share filter has to reach it too.
	const revision = SOURCES.map(({ name, source }) => [name, setsOf(source, 'for_revision').length] as const);
	const share = SOURCES.map(({ name, source }) => [name, setsOf(source, 'for_share').length] as const);

	const revisionTotal = revision.reduce((sum, [, n]) => sum + n, 0);
	const shareTotal = share.reduce((sum, [, n]) => sum + n, 0);

	assert.equal(
		revisionTotal,
		4,
		`the listing is built in ${revisionTotal} places, not 4 -- a site appeared or moved: ${JSON.stringify(revision)}`
	);
	assert.equal(
		shareTotal,
		4,
		`the share filter reaches ${shareTotal} of the 4 request builders: ${JSON.stringify(share)}`
	);
	// Site by site as well as in total, so four in one file and none in another
	// cannot pass.
	assert.deepEqual(share, revision);
});

test('T-203  the state each filter reads is per-box, not shared between them', () => {
	// The strip and the manager filter independently -- that is how the two
	// already-working marks behave, and a share filter wired to one state would
	// make pressing it in one box silently change the other.
	const page = SOURCES[2].source;
	const manager = SOURCES[1].source;
	const state = SOURCES[0].source;

	assert.match(page, /let historyForShareOnly = \$state\(false\);/);
	assert.match(page, /if \(historyForShareOnly\) params\.set\('for_share', 'true'\);/);
	assert.match(state, /forShareOnly = \$state\(false\);/);
	assert.match(state, /if \(forShareOnly\) params\.set\('for_share', 'true'\);/);
	assert.match(manager, /if \(historyManagerForShareOnly\) params\.set\('for_share', 'true'\);/);

	// And both boxes offer a way to raise it. A filter nothing can turn on is a
	// request that is never sent, whatever the counts above say.
	assert.match(page, /function setHistoryForShareOnly\(value: boolean\)/);
	assert.match(state, /setForShareOnly = \(value: boolean\) =>/);
	assert.match(read('./components/HistoryStrip.svelte'), /onSetForShareOnly\(!historyForShareOnly\)/);
	assert.match(manager, /onSetForShareOnly\(!historyManagerForShareOnly\)/);
});

test('T-203  the filter narrows with the other two rather than replacing them', () => {
	// `params.set` on three independent keys is an AND on the server. Asking for
	// the bundle AND the starred works means both; a client that cleared the
	// others when the share filter went on would be answering a question nobody
	// asked.
	for (const { name, source } of SOURCES) {
		const shareLines = source.split('\n').filter((line) => line.includes("params.set('for_share'"));
		assert.equal(
			shareLines.length,
			setsOf(source, 'for_revision').length,
			`${name} sets the share key ${shareLines.length} times and the revision key ${setsOf(source, 'for_revision').length}`
		);
		for (const line of shareLines) {
			assert.doesNotMatch(
				line,
				/params\.delete|= false/,
				`${name} clears another filter while setting the share one`
			);
		}
	}
});
