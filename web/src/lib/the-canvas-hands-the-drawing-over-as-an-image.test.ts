// Run with: npm run test:unit  (node:test, no test dependency)
//
// The canvas shows the work as an image instead of putting its markup in the
// page. Measured against production on 2026-08-16, one work was 11,068,576
// bytes and 39,789 elements, of which 24,446 carried a filter reference;
// inserted with {@html} it blocked the main thread for 3,387 ms and left all
// 39,788 nodes behind for every later layout and style pass to walk.
//
// `test:unit` is node --test with no DOM, so these read the source. That cannot
// see what a browser paints, but it can see the image being turned back into
// markup, or the blob URL losing the line that frees it.
import assert from 'node:assert/strict';
import { test } from 'node:test';
import { readFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';

const PANEL = readFileSync(
	fileURLToPath(new URL('./components/CanvasPanel.svelte', import.meta.url)),
	'utf-8'
);
const PRESENTATION = readFileSync(
	fileURLToPath(new URL('./features/canvas/CanvasPresentationOverlay.svelte', import.meta.url)),
	'utf-8'
);
const REFINEMENT = readFileSync(
	fileURLToPath(new URL('./features/canvas/CanvasRefinementWorkspace.svelte', import.meta.url)),
	'utf-8'
);
const DRAWING_VIEWS = [PANEL, PRESENTATION, REFINEMENT];

// ── T-73 ────────────────────────────────────────────────────────────────────
test('T-73  the canvas puts no drawing markup in the page', () => {
	// Every place that shows the work the canvas is holding. None of them may
	// hand the SVG text to the parser.
	assert.equal(
		DRAWING_VIEWS.reduce((count, source) => count + [...source.matchAll(/\{@html result\.svg\}/g)].length, 0),
		0,
		'the drawing is being written into the page as markup again'
	);
	// And all of them draw the image instead. Counted rather than merely
	// matched: dropping one of the three would otherwise still pass. Three, on
	// 2026-08-16: the canvas box, the presentation overlay, and the refine
	// comparison's target card.
	assert.equal(
		DRAWING_VIEWS.reduce(
			(count, source) => count + [...source.matchAll(/<img class="canvas-art" src=\{artworkUrl\}/g)].length,
			0
		),
		3,
		'every view of the current work must draw it as an image'
	);
});

// ── T-74 ────────────────────────────────────────────────────────────────────
test('T-74  the blob URL the canvas made is freed when the work changes', () => {
	// An object URL holds its blob until it is revoked. Without this the browser
	// keeps every drawing a long session has looked at -- eleven megabytes each
	// for the work this contract measured.
	const made = PANEL.indexOf('URL.createObjectURL');
	assert.ok(made > 0, 'the canvas no longer makes an object URL for the work');
	const freed = PANEL.indexOf('URL.revokeObjectURL');
	assert.ok(freed > made, 'the object URL is never revoked after it is made');
	// The revoke has to be the effect's teardown, not a stray call somewhere
	// else in the file: only a teardown runs when the work changes.
	const between = PANEL.slice(made, freed);
	assert.match(
		between,
		/return \(\) => \{/,
		'the revoke is not returned from the effect, so it does not run on a change'
	);
});
