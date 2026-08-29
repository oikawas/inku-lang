// Run with: npm run test:unit  (node:test, no test dependency)
//
// The bar under the canvas is gone.
//
// It held eight things -- a star, a hash, replay, provenance, the saijiki, and
// three separate ways to get the work out -- in a row that sat below the
// picture and acted on it from a distance. Every one of them is about the work
// on screen, so they now stand on it: the marks a reader puts on a work at the
// left, beside the caption toggle, and the rest at the right, to the left of
// the fullscreen button that was already there.
//
// The three ways out became one. SVG, PNG and the share card said three things
// where the reader wanted one, and the choice between them belongs inside the
// door rather than in front of it.
//
// T-99:  the three exports are one door, and the order they had is kept.
// T-100: the bar is gone and its controls stand in the two corner rows.
// T-101: the marks are the flags the history manager already toggles.
// T-102: each moved control answers to its own visibility group, not its row's.
// T-103: nearby works moved to the lineage tab, off the drawing they covered.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');

const PANEL = read('./components/CanvasPanel.svelte');
const ARTWORK = read('./features/canvas/CanvasArtworkWorkspace.svelte');
const HISTORY_STATE = read('./historyManagerState.svelte.ts');
const LINEAGE = read('./components/LineagePanel.svelte');
const PAGE = read('../routes/+page.svelte');

/**
 * One corner row of the canvas, from its opening tag to its matching close.
 *
 * Counted by depth rather than cut at the first `</div>`: the right row now
 * contains the export menu, which is divs inside divs, and a shallow cut ends
 * the region in the middle of it -- leaving the fullscreen button outside a
 * region that really does contain it.
 */
function cornerRow(side: 'left' | 'right'): string {
	const start = ARTWORK.indexOf(`<div class="canvas-corner-controls canvas-corner-${side}"`);
	assert.ok(start > 0, `the ${side} corner row is gone`);
	let depth = 0;
	for (let i = start; i < ARTWORK.length; i += 1) {
		if (ARTWORK.startsWith('<div', i)) depth += 1;
		else if (ARTWORK.startsWith('</div>', i)) {
			depth -= 1;
			if (depth === 0) return ARTWORK.slice(start, i);
		}
	}
	throw new Error(`the ${side} corner row never closes`);
}

/** The order the given markers appear in, as their indexes in `region`. */
function positionsOf(region: string, markers: string[]): number[] {
	return markers.map((marker) => {
		const at = region.indexOf(marker);
		assert.notEqual(at, -1, `${marker} is not in the region`);
		return at;
	});
}

// ------------------------------------------------------- T-99 (one door out)

test('T-99: SVG, PNG and the card leave through one button', () => {
	// One button, one menu. Two of the three used to carry a menu of their own
	// and the third was a button that acted at once, which is why the row read
	// as three unrelated things.
	assert.equal((ARTWORK.match(/class="canvas-icon-btn canvas-export-btn"/g) ?? []).length, 1);
	assert.equal((ARTWORK.match(/<div class="export-menu"/g) ?? []).length, 1);
	// And the separate doors are gone, by their own names.
	assert.doesNotMatch(ARTWORK, /class="png-wrap"/);
	assert.doesNotMatch(ARTWORK, /svgMenuOpen/);
	assert.doesNotMatch(ARTWORK, /pngMenuOpen/);
	assert.doesNotMatch(PAGE, /pngMenuOpen|pngWrapEl/);
});

test('T-99: the menu keeps the order the three buttons stood in', () => {
	const menu = ARTWORK.slice(ARTWORK.indexOf('<div class="export-menu"'));
	const [svg, png, card] = positionsOf(menu, ['onDownloadSVG', 'onDownloadPNG', 'onDownloadCard']);
	assert.ok(svg < png && png < card, 'the three ways out were reordered by the merge');
});

test('T-99: the menu closes on a press outside itself, not outside the row', () => {
	// The wrap the page measures against has to be the menu's own box. Bound to
	// the corner row instead, a press on any other button in that row would
	// count as inside and leave the menu standing open.
	assert.match(ARTWORK, /<div class="canvas-export" bind:this=\{exportWrapEl\}>/);
	assert.doesNotMatch(ARTWORK, /canvas-corner-right" bind:this=\{exportWrapEl\}/);
	assert.match(PAGE, /if \(exportMenuOpen && exportWrapEl && !exportWrapEl\.contains\(e\.target as Node\)\) exportMenuOpen = false;/);
});

// -------------------------------------------------- T-100 (the bar is gone)

test('T-100: the bar under the canvas no longer exists', () => {
	assert.doesNotMatch(ARTWORK, /class="status-bar"/);
	assert.doesNotMatch(ARTWORK, /class="status-spacer"/);
	// Its two label-shaped button styles went with it.
	assert.doesNotMatch(ARTWORK, /\.generation-info-button \{/);
	assert.doesNotMatch(ARTWORK, /\.status-hash-btn \{/);
});

test('T-100: the marks stand at the left, after the caption toggle', () => {
	const left = cornerRow('left');
	const [caption, star, revision] = positionsOf(left, [
		'canvas-caption-btn',
		'canvas-star-btn',
		'canvas-revision-btn'
	]);
	assert.ok(caption < star, 'the star is to the left of the caption toggle');
	assert.ok(star < revision, 'the revision mark is not beside the star');
});

test('T-100: the rest stand at the right, and fullscreen is still last', () => {
	const right = cornerRow('right');
	const order = positionsOf(right, [
		'canvas-hash-btn',
		'canvas-replay-btn',
		'canvas-provenance-btn',
		'canvas-saijiki-btn',
		'canvas-export-btn',
		'canvas-presentation-btn'
	]);
	for (let i = 1; i < order.length; i += 1) {
		assert.ok(order[i - 1] < order[i], `control ${i} is out of order in the right row`);
	}
	// The fullscreen button keeps the corner it has always had: it is last, so
	// nothing that moved in pushed it away from the edge.
	assert.equal(order[order.length - 1], Math.max(...order));
});

test('T-100: the lower button tooltips stand in front of the caption', () => {
	// Tooltip raises its own wrapper, but that value stays inside the row's
	// stacking context. The row itself must therefore outrank the caption.
	const controls = ARTWORK.match(/\.canvas-corner-controls \{[\s\S]*?\}/)?.[0] ?? '';
	const caption = ARTWORK.match(/\.instruction-caption \{[\s\S]*?\}/)?.[0] ?? '';
	const controlsLayer = Number(controls.match(/z-index:\s*(\d+)/)?.[1]);
	const captionLayer = Number(caption.match(/z-index:\s*(\d+)/)?.[1]);
	assert.ok(controlsLayer > captionLayer, 'the caption still paints over a lower button tooltip');
});

// ------------------------------------------------ T-101 (the marks are real)

test('T-101: the two marks are the two flags a work carries', () => {
	const left = cornerRow('left');
	// Not new state: the star and the revision mark are the same two columns
	// the history manager toggles, reached through the same two handlers.
	assert.match(left, /onToggleStar\(statusHistoryItem, event\)/);
	assert.match(left, /onToggleForRevision\(statusHistoryItem, event\)/);
	const call = PAGE.slice(PAGE.indexOf('<CanvasPanel'), PAGE.indexOf('/>', PAGE.indexOf('<CanvasPanel')));
	assert.match(call, /onToggleStar=\{toggleHistoryStar\}/);
	assert.match(call, /onToggleForRevision=\{toggleHistoryForRevision\}/);
	assert.match(PAGE, /const toggleHistoryStar = historyMutations\.toggleStar/);
	assert.match(PAGE, /const toggleHistoryForRevision = historyMutations\.toggleForRevision/);
	// A newly saved result can be on the canvas before it appears in the history
	// strip. Its mark still needs a reactive projection or the PATCH succeeds
	// while this button redraws itself as unstarred.
	assert.match(PAGE, /applyCurrentResultStarState: \(item\) =>/);
	assert.match(PAGE, /currentResultStarState\?\.id === historyId/);
	// The canvas has to be able to read the flag it draws, or the mark would
	// never come back on for a work that already carries it.
	assert.match(HISTORY_STATE, /for_revision\?: boolean;/);
	assert.match(left, /class:marked=\{!!statusHistoryItem\?\.for_revision\}/);
	assert.match(left, /class:marked=\{!!statusHistoryItem\?\.starred\}/);
});

test('T-101: a work with no id can be marked with neither', () => {
	const left = cornerRow('left');
	const marks = left.split('canvas-star-btn')[1] ?? '';
	assert.equal(
		(marks.match(/disabled=\{!statusHistoryItem\?\.id\}/g) ?? []).length,
		2,
		'one of the two marks can be pressed on a work that was never saved'
	);
});

// ------------------------------- T-102 (each control keeps its own group)

test('T-102: the visibility rules name buttons, never a whole corner row', () => {
	// The two rows carry buttons from two different groups now. A rule on a row
	// would hide one group's buttons whenever the other group was switched off,
	// which is reachable: a custom mode may keep detail_status and drop
	// work_tools.
	const rules = PAGE.slice(PAGE.indexOf('/* UI modes change visibility only.'));
	const block = rules.slice(0, rules.indexOf('display: none;'));
	assert.doesNotMatch(block, /:global\(\.canvas-corner-controls\)/);
	assert.doesNotMatch(block, /:global\(\.canvas-corner-(left|right)\)/);

	// Every control that moved is named exactly once, under one group.
	const groups: Record<string, string> = {
		'canvas-hash-btn': 'ui-hide-detail-status',
		'canvas-provenance-btn': 'ui-hide-detail-status',
		'canvas-star-btn': 'ui-hide-work-tools',
		'canvas-revision-btn': 'ui-hide-work-tools',
		// The share mark's socket -- offered only when I-191 lands (T-105).
		'canvas-share-btn': 'ui-hide-work-tools',
		'canvas-replay-btn': 'ui-hide-work-tools',
		'canvas-saijiki-btn': 'ui-hide-work-tools',
		'canvas-caption-btn': 'ui-hide-work-tools',
		'canvas-presentation-btn': 'ui-hide-work-tools'
	};
	for (const [cls, group] of Object.entries(groups)) {
		const named = block.match(new RegExp(`\\.(ui-hide-[a-z-]+) :global\\(\\.${cls}\\)`, 'g')) ?? [];
		assert.equal(named.length, 1, `${cls} is named ${named.length} times, not once`);
		assert.match(named[0], new RegExp(`^\\.${group} `), `${cls} is under the wrong group`);
	}

	// The export button is the one moved control that no group names, by the
	// author's ruling of 2026-08-16: hiding it took the share card out of the
	// simple UI along with SVG and PNG. It stays and narrows what it opens
	// onto instead, which is T-107's business. Named here so that the count
	// above still covers every control on the rows -- this one by its absence.
	assert.doesNotMatch(block, /:global\(\.canvas-export\)/);
});

// --------------------------------------- T-103 (nearby works left the canvas)

test('T-103: nearby works are shown by the lineage tab', () => {
	assert.match(LINEAGE, /class="nearby-mirror"/);
	assert.match(LINEAGE, /onOpenNearbyHistory\?\.\(item\.id\)/);
	// The canvas hands them on rather than drawing them.
	assert.doesNotMatch(PANEL, /class="nearby-mirror"/);
	assert.doesNotMatch(PANEL, /class="nearby-thumb"/);
	assert.match(PANEL, /<LineagePanel [^>]*\{nearbyHistory\} \{onOpenNearbyHistory\}/);
});

test('T-103: the strip is in the flow there, not floating over a drawing', () => {
	// On the canvas it was positioned over the picture it was offered beside.
	// The lineage tab has room, so it is a row like any other -- and the one
	// literal colour it carried is a token now, the way the paper is elsewhere.
	const rule = LINEAGE.match(/\.nearby-mirror \{[^}]*\}/);
	assert.ok(rule, 'the strip lost its rule');
	assert.doesNotMatch(rule[0], /position: absolute/);
	assert.doesNotMatch(LINEAGE, /\.nearby-thumb \{[^}]*background: white/);
	assert.match(LINEAGE, /\.nearby-thumb \{[^}]*var\(--canvas-paper\)/);
	// The history group still hides it, as it did on the canvas.
	assert.match(PAGE, /\.ui-hide-history :global\(\.nearby-mirror\)/);
});

// ------------------------- T-107 (the simple UI keeps a door, and it is the card)
//
// Added 2026-08-16 by author's ruling, after the merge of the four stages
// above: "in a simple UI, show the export button as a button that calls the
// share card alone."
//
// The merge of the three ways out had taken the card off the simple UI with
// SVG and PNG, because a merged door cannot be half hidden. The ruling keeps
// the door and narrows what it opens onto, which is the one of the three that
// is not a work tool: the card is how a work leaves for someone else.

test('T-107: no UI mode hides the export button any more', () => {
	// The rule that used to hide it is what took the card away.
	assert.doesNotMatch(PAGE, /:global\(\.canvas-export\)/);
	// The other work tools on the same row are still named, so this case is not
	// satisfied by a page that stopped hiding anything at all.
	assert.match(PAGE, /\.ui-hide-work-tools :global\(\.canvas-star-btn\)/);
	assert.match(PAGE, /\.ui-hide-work-tools :global\(\.canvas-saijiki-btn\)/);
});

test('T-107: the page tells the canvas which of the two jobs the button has', () => {
	// The visibility of the work tools is what decides it, and it is read from
	// the same derived value the hide classes are read from -- not a second
	// copy of the rule that could drift from it.
	assert.match(PAGE, /exportCardOnly=\{!session\.uiVisibility\.work_tools\}/);
	assert.match(PAGE, /class:ui-hide-work-tools=\{!session\.uiVisibility\.work_tools\}/);
});

test('T-107: with the work tools gone the button calls the card, not a menu', () => {
	assert.match(ARTWORK, /if \(exportCardOnly\) onDownloadCard\(\);/);
	assert.match(ARTWORK, /else exportMenuOpen = !exportMenuOpen;/);
	// A menu of one is still a menu. The panel must not be able to open it in
	// that state, whatever the bound flag happens to hold.
	assert.match(ARTWORK, /\{#if exportMenuOpen && !exportCardOnly\}/);
	// And it must not announce a menu it will not open.
	assert.match(ARTWORK, /aria-haspopup=\{exportCardOnly \? undefined : 'menu'\}/);
});

test('T-107: in that state the button is disabled exactly when the card is', () => {
	// The menu entry is disabled without a saved work or while one is building.
	// A door that leads only there must refuse in the same two cases -- with
	// `!result` alone it would be pressable and then do nothing.
	assert.match(
		ARTWORK,
		/disabled=\{exportCardOnly \? \(!currentHistoryId \|\| cardExportBusy\) : !result\}/
	);
	assert.match(ARTWORK, /disabled=\{!currentHistoryId \|\| cardExportBusy\}/);
	// It says what it does, too: the card's own label, not "export".
	assert.match(ARTWORK, /aria-label=\{exportCardOnly \? t\(\)\.historyCardExport : t\(\)\.exportLabel\}/);
});
