// Run with: npm run test:unit  (node:test, no test dependency)
//
// Contract 2, stage 5. The listing draws a PNG baked from each work's stored
// SVG instead of the SVG itself. A work that has no thumbnail yet -- every work
// the moment it is drawn, and every work at all until the first rebuild has run
// -- must still appear, drawn from the SVG the client already has.
//
// The URL decision is a function so these can drive it. The fallback itself
// lives in a component, and `test:unit` is node --test with no DOM, so that
// part reads the source the way the trash-view gate next door does: it cannot
// see what a browser paints, but it can see the fallback branch being removed.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

import { thumbnailScale, thumbnailSrc } from './thumbnailSource.ts';

const ORDINARY = { hidpi: false, devicePixelRatio: 1 };
const WORK = { id: 'work-1', render_hash: 'abc123' };

// ── T-12, the PNG side ──────────────────────────────────────────────────────
test('a saved work is drawn from its thumbnail', () => {
	const src = thumbnailSrc(WORK, ORDINARY);
	assert.ok(src);
	const asked = new URL(src, 'http://localhost');
	assert.equal(asked.pathname, '/api/history/work-1/thumb');
	assert.equal(asked.searchParams.get('scale'), '1');
});

// ── T-12, the SVG side ──────────────────────────────────────────────────────
test('a work that cannot have a thumbnail asks for none', () => {
	// No id: the work has not been saved, so there is nothing to have baked a
	// picture of. The caller draws the SVG it is holding.
	assert.equal(thumbnailSrc({ id: undefined, render_hash: null }, ORDINARY), null);
});

test('a listing may hold both kinds at once', () => {
	const mixed = [WORK, { id: undefined, render_hash: null }, { id: 'work-2', render_hash: null }];
	const decided = mixed.map((item) => thumbnailSrc(item, ORDINARY));
	assert.equal(decided.filter((src) => src !== null).length, 2);
	assert.equal(decided.filter((src) => src === null).length, 1);
});

// ── The source names the picture, so a rebuilt one is not hidden by the cache ─
test('the URL carries the render hash the thumbnail was baked from', () => {
	const before = new URL(thumbnailSrc(WORK, ORDINARY)!, 'http://x');
	const after = new URL(thumbnailSrc({ ...WORK, render_hash: 'def456' }, ORDINARY)!, 'http://x');
	assert.equal(before.searchParams.get('v'), 'abc123');
	assert.notEqual(before.href, after.href, 'a rebuilt picture must not reuse the cached address');

	// A work saved before render hashes existed still has an address.
	assert.ok(thumbnailSrc({ id: 'old', render_hash: null }, ORDINARY));
});

// ── T-10, from the client's side ────────────────────────────────────────────
test('the second size is asked for only where it exists and is used', () => {
	assert.equal(thumbnailScale({ hidpi: true, devicePixelRatio: 2 }), 2);
	// Off on the server: asking would be a 404 for every thumbnail on screen.
	assert.equal(thumbnailScale({ hidpi: false, devicePixelRatio: 2 }), 1);
	// On, but the screen cannot show it.
	assert.equal(thumbnailScale({ hidpi: true, devicePixelRatio: 1 }), 1);
});

// ── The component keeps the way back ────────────────────────────────────────
const THUMBNAIL_SOURCE = readFileSync(
	fileURLToPath(new URL('./components/HistoryThumbnail.svelte', import.meta.url)),
	'utf-8'
);

test('a thumbnail that fails to load falls back to the drawing', () => {
	// The <img> must report its failure...
	assert.match(THUMBNAIL_SOURCE, /onerror=\{\(\) => \(thumbMissing = true\)\}/);
	// ...and the branch it falls back to must still draw the SVG.
	assert.match(THUMBNAIL_SOURCE, /\{:else\}\s*\{@html clippedSvg\}/);
	// The flag has to reach the decision, or reporting the failure changes
	// nothing and the work stays blank.
	assert.match(THUMBNAIL_SOURCE, /thumbMissing \? null : thumbnailSrc\(/);
});

test('the work keeps its shape when it is a PNG', () => {
	// The SVG path letterboxes by default (preserveAspectRatio), so the PNG has
	// to as well or the listing changes appearance on the day it starts using
	// thumbnails.
	assert.match(THUMBNAIL_SOURCE, /\.history-thumbnail img \{[^}]*object-fit: contain;/);
});

// ── Every side-by-side listing goes through this one component ──────────────
// Measured on 28ce4237: seven call sites, in five files. Stated here so that a
// new grid of works drawn by hand -- which would keep carrying whole SVGs --
// shows up as a failure rather than as a listing that is quietly still slow.
test('the listings that show works side by side all use this component', () => {
	const CALL_SITES: Record<string, number> = {
		'components/HistoryStrip.svelte': 1,
		'components/HistoryManager.svelte': 4,
		'components/LineagePanel.svelte': 1,
		'components/AIRefineModal.svelte': 1
	};
	let total = 0;
	for (const [file, expected] of Object.entries(CALL_SITES)) {
		const source = readFileSync(fileURLToPath(new URL(`./${file}`, import.meta.url)), 'utf-8');
		const found = source.match(/<HistoryThumbnail\b/g)?.length ?? 0;
		assert.equal(found, expected, `${file} draws ${found} thumbnails, expected ${expected}`);
		total += found;
	}
	assert.equal(total, 7);
});

// ── Stage 6: who asks the listing for what ──────────────────────────────────
// A roll-call, not a style check. The flag defaults to true, so a sender that
// writes nothing keeps receiving every drawing and nothing goes wrong loudly --
// it is just slow, which is the defect this contract exists to remove. Counted
// on 28ce4237: three GET senders in the web client.
const SENDERS = [
	{
		file: '../routes/+page.svelte',
		what: "the strip's listing",
		pattern: /limit: String\(listLimit\),\s*(?:\/\/[^\n]*\n\s*)*include_svg: 'false'/,
		sendsFalse: true
	},
	{
		file: './historyManagerState.svelte.ts',
		what: "the manager's listing",
		pattern: /limit: String\(pageSize\),[\s\S]{0,200}?include_svg: 'false'/,
		sendsFalse: true
	}
];

test('the two listings that draw thumbnails ask for no drawings', () => {
	for (const sender of SENDERS) {
		const source = readFileSync(fileURLToPath(new URL(sender.file, import.meta.url)), 'utf-8');
		assert.match(source, sender.pattern, `${sender.what} must ask for no drawings`);
	}
});

test('every other listing sender is accounted for', () => {
	// The trash page is the one GET that still asks for drawings, and it asks
	// for a hundred works at a time. Contract 2 says to leave it alone, so it is
	// named here rather than silently left out: a fourth sender appearing makes
	// this fail and has to be decided about.
	const page = readFileSync(fileURLToPath(new URL('../routes/+page.svelte', import.meta.url)), 'utf-8');
	const manager = readFileSync(fileURLToPath(new URL('./historyManagerState.svelte.ts', import.meta.url)), 'utf-8');
	const getters = [...page.matchAll(/apiFetch\(`\/api\/history\?/g)].length
		+ [...manager.matchAll(/apiFetch\(`\/api\/history\?/g)].length;
	assert.equal(getters, 3, 'three senders ask the listing for works');

	assert.match(page, /\/api\/history\?offset=0&limit=100&trashed=true/, 'the trash page still asks for drawings');
});
