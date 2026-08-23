// Run with: npm run test:unit  (node:test, no test dependency)
//
// The app has two drawers that slide in over the canvas from the right: the
// saijiki and the provenance panel. They behaved differently for no reason the
// author could see -- one closed when you pressed outside it and the other did
// not, one slid in and the other appeared whole.
//
// T-44 (the saijiki closes on a press outside, and its own button still
// toggles it), T-45 (the provenance drawer is uncovered from the right edge
// over the saijiki's own duration and curve).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const SAIJIKI = read('./components/SaijikiDrawer.svelte');
const PANEL = read('./components/CanvasPanel.svelte');
const INFO = read('./features/canvas/CanvasGenerationInfo.svelte');

// ------------------------------------------------------------------- T-44

test('T-44  a press outside the saijiki closes it', () => {
	assert.match(SAIJIKI, /<svelte:window/);
	assert.match(SAIJIKI, /onpointerdown=/);
	// It asks its own element, so nothing inside the drawer closes it.
	assert.match(SAIJIKI, /bind:this=\{drawerEl\}/);
	assert.match(SAIJIKI, /drawerEl\?\.contains\(target\)/);
	assert.match(SAIJIKI, /onClose\(\)/);
	// And it does nothing at all while shut.
	assert.match(SAIJIKI, /if \(!open\) return;/);
});

test('T-44  the button that opens it is not "outside"', () => {
	// pointerdown runs before click. Close on the button's own pointerdown and
	// the click that follows toggles it straight back open, so the drawer could
	// never be closed from the button it was opened with.
	assert.match(SAIJIKI, /target\.closest\?\.\('\[data-saijiki-toggle\]'\)/);
	// Both halves of that contract, so neither side can be renamed alone.
	assert.match(PANEL, /data-saijiki-toggle/);
	const button = PANEL.slice(PANEL.indexOf('data-saijiki-toggle'));
	assert.match(button.slice(0, 200), /onclick=\{onToggleSaijiki\}/);
});

test('T-44  the marker is an attribute, not a style class', () => {
	// `saijiki-open-btn` is a class, and a class is a style: renaming it is a
	// styling change that would silently take the close behaviour with it.
	assert.doesNotMatch(SAIJIKI, /closest\?\.\('\.[a-z-]+'\)/);
});

// ------------------------------------------------------------------- T-45

/** The one timing the two drawers are supposed to share. */
const REVEAL = '0.25s cubic-bezier(0.4, 0, 0.2, 1)';

test('T-45  the provenance drawer is revealed, not popped into place', () => {
	// It used to be mounted by {#if}, so it arrived whole with no animation at
	// all. It stays mounted now and is clipped shut.
	assert.match(PANEL, /open=\{generationInfoOpen\}/);
	assert.match(INFO, /class:open/);
	assert.doesNotMatch(PANEL, /\{#if generationInfoOpen\}/);
	assert.match(INFO, /\.generation-info \{[^}]*clip-path: inset\(0 0 0 100%\)/);
	assert.match(INFO, /\.generation-info\.open \{[^}]*clip-path: inset\(0 0 0 0\)/);
});

test('T-45  it takes the saijiki drawer\'s own duration and curve', () => {
	const provenance = INFO.match(/\.generation-info \{[^}]*transition: clip-path ([^;]+);/);
	assert.ok(provenance, 'the provenance drawer has no reveal');
	const saijiki = SAIJIKI.match(/\.saijiki-drawer \{[^}]*transition: width ([^;]+);/);
	assert.ok(saijiki, 'the saijiki drawer has no reveal');
	// Written the same way in both files, so a change to one is visible as a
	// difference from the other rather than as a drawer that feels wrong.
	const normalise = (value: string) => value.replace(/\s+/g, '');
	assert.equal(normalise(provenance[1]), normalise(REVEAL));
	assert.equal(normalise(saijiki[1]), normalise(REVEAL));
});

test('T-45  and a drawer that is shut takes no presses', () => {
	// Clipping hides it without collapsing the box, so the box would otherwise
	// still swallow clicks meant for the canvas behind it.
	assert.match(INFO, /\.generation-info \{[^}]*pointer-events: none/);
	assert.match(INFO, /\.generation-info\.open \{[^}]*pointer-events: all/);
	assert.match(INFO, /aria-hidden=\{!open\}/);
});
