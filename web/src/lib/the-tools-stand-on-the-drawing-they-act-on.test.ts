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
	const start = PANEL.indexOf(`<div class="canvas-corner-controls canvas-corner-${side}"`);
	assert.ok(start > 0, `the ${side} corner row is gone`);
	let depth = 0;
	for (let i = start; i < PANEL.length; i += 1) {
		if (PANEL.startsWith('<div', i)) depth += 1;
		else if (PANEL.startsWith('</div>', i)) {
			depth -= 1;
			if (depth === 0) return PANEL.slice(start, i);
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
	assert.equal((PANEL.match(/class="canvas-icon-btn canvas-export-btn"/g) ?? []).length, 1);
	assert.equal((PANEL.match(/<div class="export-menu"/g) ?? []).length, 1);
	// And the separate doors are gone, by their own names.
	assert.doesNotMatch(PANEL, /class="png-wrap"/);
	assert.doesNotMatch(PANEL, /svgMenuOpen/);
	assert.doesNotMatch(PANEL, /pngMenuOpen/);
	assert.doesNotMatch(PAGE, /pngMenuOpen|pngWrapEl/);
});

test('T-99: the menu keeps the order the three buttons stood in', () => {
	const menu = PANEL.slice(PANEL.indexOf('<div class="export-menu"'));
	const [svg, png, card] = positionsOf(menu, ['onDownloadSVG', 'onDownloadPNG', 'downloadCardFromCanvas']);
	assert.ok(svg < png && png < card, 'the three ways out were reordered by the merge');
});

test('T-99: the menu closes on a press outside itself, not outside the row', () => {
	// The wrap the page measures against has to be the menu's own box. Bound to
	// the corner row instead, a press on any other button in that row would
	// count as inside and leave the menu standing open.
	assert.match(PANEL, /<div class="canvas-export" bind:this=\{exportWrapEl\}>/);
	assert.doesNotMatch(PANEL, /canvas-corner-right" bind:this=\{exportWrapEl\}/);
	assert.match(PAGE, /if \(exportMenuOpen && exportWrapEl && !exportWrapEl\.contains\(e\.target as Node\)\) exportMenuOpen = false;/);
});

// -------------------------------------------------- T-100 (the bar is gone)

test('T-100: the bar under the canvas no longer exists', () => {
	assert.doesNotMatch(PANEL, /class="status-bar"/);
	assert.doesNotMatch(PANEL, /class="status-spacer"/);
	// Its two label-shaped button styles went with it.
	assert.doesNotMatch(PANEL, /\.generation-info-button \{/);
	assert.doesNotMatch(PANEL, /\.status-hash-btn \{/);
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
	// The canvas has to be able to read the flag it draws, or the mark would
	// never come back on for a work that already carries it.
	assert.match(PANEL, /for_revision\?: boolean;/);
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
		'canvas-export': 'ui-hide-work-tools',
		'canvas-caption-btn': 'ui-hide-work-tools',
		'canvas-presentation-btn': 'ui-hide-work-tools'
	};
	for (const [cls, group] of Object.entries(groups)) {
		const named = block.match(new RegExp(`\\.(ui-hide-[a-z-]+) :global\\(\\.${cls}\\)`, 'g')) ?? [];
		assert.equal(named.length, 1, `${cls} is named ${named.length} times, not once`);
		assert.match(named[0], new RegExp(`^\\.${group} `), `${cls} is under the wrong group`);
	}
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
