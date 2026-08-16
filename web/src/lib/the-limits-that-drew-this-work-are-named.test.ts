// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-107 of 契約 a-work-redraws-under-the-limits-it-was-drawn-under (ledger I-154).
//
// Nine settings decide how much ink one work may carry. Two of them could say
// they had taken effect and seven took effect in silence: lowering one halved a
// picture -- 2,149,767 bytes to 1,038,689 -- with `render_limit_notes` None on
// both. The server now writes one line per limit that bound. This checks the
// page reads them the way it reads the expansion warnings beside them, and that
// the section is absent when there is nothing to say.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { limitNoteName, limitNotesToShow } from './limitNotes.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const page = fs.readFileSync(path.join(here, '..', 'routes', '+page.svelte'), 'utf8');

test('T-107  the notes a finished drawing carries are the ones shown', () => {
	assert.deepEqual(
		limitNotesToShow({
			render_limit_notes: [
				'represented_count_max: a group of 600 is above the 120 a reader can count, so it is drawn as 120',
				'max_expanded_primitives: hard ceiling 400 applied to the whole work'
			]
		}),
		[
			'represented_count_max: a group of 600 is above the 120 a reader can count, so it is drawn as 120',
			'max_expanded_primitives: hard ceiling 400 applied to the whole work'
		]
	);
});

test('T-107  nothing to say renders nothing at all', () => {
	// An empty frame reads as "something happened here" when nothing did, which
	// is the rule `pluginWarningsToShow` was written to. A work drawn well
	// inside every limit is the ordinary case, so this is most drawings.
	assert.deepEqual(limitNotesToShow(null), []);
	assert.deepEqual(limitNotesToShow(undefined), []);
	assert.deepEqual(limitNotesToShow({}), []);
	assert.deepEqual(limitNotesToShow({ render_limit_notes: null }), []);
	assert.deepEqual(limitNotesToShow({ render_limit_notes: [] }), []);
	// A blank line is not a note. One would draw the frame and say nothing.
	assert.deepEqual(limitNotesToShow({ render_limit_notes: ['', '   '] }), []);
});

test('T-107  each line names which of the nine took effect', () => {
	// The name leads the line so the nine can be told apart by a reader that
	// only has the strings. "The ink halved" was the whole of what the two
	// existing notes could say, and neither of them named a setting.
	assert.equal(
		limitNoteName('represented_count_max: a group of 600 is drawn as 120'),
		'represented_count_max'
	);
	assert.equal(limitNoteName('instruction list capped at 64; 3 dropped'), null);
	assert.equal(limitNoteName(''), null);
});

test('T-107  the page shows them, from the one read point every draw path sets', () => {
	// The section has to be wired to `result`, the state whatever drew last
	// assigns -- a surface fed from the paint route alone would stay blank for
	// a redraw, which is the path this contract exists for.
	assert.match(page, /const limitNotesShown = \$derived\(limitNotesToShow\(result\)\);/);
	assert.match(page, /\{#if limitNotesShown\.length > 0 && inputMode === 'single'\}/);
	assert.match(page, /\{#each limitNotesShown as note\}/);
	assert.match(page, /\{t\(\)\.renderLimitNotesTitle\}/);
});

test('T-107  the heading is translated and the lines are not', () => {
	// The lines are diagnostics the server wrote, and the plugin warnings beside
	// them are shown untranslated for the same reason. Only the heading is a
	// word this application chose, so only the heading is in the two catalogues.
	const ja = fs.readFileSync(path.join(here, 'i18n', 'ja.ts'), 'utf8');
	const en = fs.readFileSync(path.join(here, 'i18n', 'en.ts'), 'utf8');
	const types = fs.readFileSync(path.join(here, 'i18n', 'types.ts'), 'utf8');
	assert.match(ja, /renderLimitNotesTitle: '/);
	assert.match(en, /renderLimitNotesTitle: '/);
	assert.match(types, /renderLimitNotesTitle: string;/);

	const source = fs.readFileSync(path.join(here, 'limitNotes.ts'), 'utf8');
	assert.equal(/^\s*import .*i18n/m.test(source), false, 'the reader must not reach for a catalogue');
});
