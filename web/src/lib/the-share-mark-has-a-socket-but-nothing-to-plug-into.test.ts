// Run with: npm run test:unit  (node:test, no test dependency)
//
// A third mark was asked for beside the star and the revision mark: "this work
// may be shared". The flag it would stand on does not exist. `starred` and
// `for_revision` are columns on `history`; `shared` is a derived marker meaning
// the row belongs to someone else. The real thing is ledger I-191 -- server,
// web and cli -- and I-191 still holds two undecided questions.
//
// So web builds the socket and stops there. The mark appears the moment a work
// arrives carrying the field and a handler is wired, and not before: a mark
// that cannot be saved says the work is marked when nothing recorded it, which
// is worse than no mark at all.
//
// T-104: the socket decides on the field being there, not on it being true.
// T-105: nothing is offered while nothing can save it, and both halves gate it.
// T-106: the words and the visibility rule are in place for the follow-up.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { shareTargetOf } from './shareTarget.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');

const PANEL = read('./components/CanvasPanel.svelte');
const PAGE = read('../routes/+page.svelte');
const JA = read('./i18n/ja.ts');
const EN = read('./i18n/en.ts');
const TYPES = read('./i18n/types.ts');

// ------------------------------------------------- T-104 (absent vs. false)

test('T-104: an absent field is a server that does not know the flag', () => {
	// This is the whole point of the socket. `undefined` means the column is
	// not there yet; `false` means it is there and this work is not marked.
	// Collapsing the two -- reading `!item.for_share` -- would hide the mark on
	// exactly the works allowed to carry it, and the follow-up would look
	// broken on arrival.
	assert.deepEqual(shareTargetOf({ id: 'w1' }), { supported: false, marked: false, pressable: false });
	assert.deepEqual(shareTargetOf({ id: 'w1', for_share: false }), { supported: true, marked: false, pressable: true });
	assert.deepEqual(shareTargetOf({ id: 'w1', for_share: true }), { supported: true, marked: true, pressable: true });
});

test('T-104: a work nobody saved has nothing to mark', () => {
	assert.deepEqual(shareTargetOf({ for_share: false }), { supported: true, marked: false, pressable: false });
	assert.deepEqual(shareTargetOf({ for_share: true }), { supported: true, marked: true, pressable: false });
	// And no work at all is not a work with the flag off.
	assert.deepEqual(shareTargetOf(null), { supported: false, marked: false, pressable: false });
	assert.deepEqual(shareTargetOf(undefined), { supported: false, marked: false, pressable: false });
});

test('T-104: the decision is made in one place, from the field itself', () => {
	const source = read('./shareTarget.ts');
	assert.match(source, /typeof work\?\.for_share === 'boolean'/);
	// A truthiness test here is the defect this file exists to prevent.
	assert.doesNotMatch(source, /supported = !!work\?\.for_share/);
	assert.doesNotMatch(source, /supported = Boolean\(work\?\.for_share\)/);
});

// ------------------------------------------- T-105 (nothing is offered yet)

test('T-105: the mark is behind both the flag and a handler', () => {
	assert.match(PANEL, /\{#if shareTarget\.supported && onToggleForShare\}/);
	assert.match(PANEL, /const shareTarget = \$derived\(shareTargetOf\(statusHistoryItem\)\);/);
	// The canvas must be able to read the field, or `supported` is false even
	// after the server starts sending it.
	assert.match(PANEL, /for_share\?: boolean;/);
});

test('T-105: nothing hands the canvas a way to save it, so nothing shows', () => {
	// The page is the half that is deliberately missing: there is no endpoint
	// to call. When I-191 lands it passes a handler here and the mark appears
	// with no further change to the canvas.
	const call = PAGE.slice(PAGE.indexOf('<CanvasPanel'), PAGE.indexOf('/>', PAGE.indexOf('<CanvasPanel')));
	assert.match(call, /onToggleForRevision=\{toggleHistoryForRevision\}/, 'the wired marks moved');
	assert.doesNotMatch(call, /onToggleForShare/, 'a share handler was wired before there is anything to save to');
	// And the prop defaults to nothing rather than to a function that pretends.
	assert.match(PANEL, /onToggleForShare = null,/);
});

test('T-105: the socket names where the rest of the work is written down', () => {
	// The next session finds the ledger id from the code, not from a memory of
	// this conversation.
	const source = read('./shareTarget.ts');
	assert.match(source, /I-191/);
	assert.match(PANEL, /I-191/);
});

// ------------------------------------------ T-106 (ready for the follow-up)

test('T-106: the two words stand in all three i18n faces', () => {
	for (const [name, source] of [['ja', JA], ['en', EN]] as const) {
		assert.match(source, /shareTargetOn: '.+',/, `${name} has no shareTargetOn`);
		assert.match(source, /shareTargetOff: '.+',/, `${name} has no shareTargetOff`);
	}
	assert.match(TYPES, /shareTargetOn: string;/);
	assert.match(TYPES, /shareTargetOff: string;/);
});

test('T-106: the mark answers to the same visibility group as the other two', () => {
	const rules = PAGE.slice(PAGE.indexOf('/* UI modes change visibility only.'));
	const block = rules.slice(0, rules.indexOf('display: none;'));
	const named = block.match(/\.(ui-hide-[a-z-]+) :global\(\.canvas-share-btn\)/g) ?? [];
	assert.equal(named.length, 1, `the share mark is named ${named.length} times, not once`);
	assert.match(named[0], /^\.ui-hide-work-tools /);
});
