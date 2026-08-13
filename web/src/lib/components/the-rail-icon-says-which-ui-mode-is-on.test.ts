// Run with: npm run test:unit  (node:test, no test dependency)
//
// The rail's UI mode button carried the same picture in all three modes -- a
// frame with one divider -- so it said neither what it did nor which mode was
// on. It also carried a 4x2px dot that is not visible at the 22px the rail
// draws its icons at. The rail is collapsed by default and only draws the mode
// name when expanded, so the icon was the whole of what a reader got.
//
// It is three bars of falling length now, and how many of them are solid is
// which mode is on (author's choice, 2026-08-13, from three candidates seen at
// their real size).
//
// T-53 (the icon is drawn from the mode, and the three modes are drawn
// differently), T-54 (the mark that said nothing is gone).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import { normalizeUiMode } from '../uiMode.ts';

const RAIL = readFileSync(new URL('./AppRail.svelte', import.meta.url), 'utf8');

/** The three modes uiMode.ts can hand the rail. */
const MODES = ['simple', 'full', 'custom'];

// ------------------------------------------------------------------- T-53

test('T-53  the icon is drawn from the mode that is on', () => {
	// Not a static class: the mode is written into the element, so a rail that
	// had gone back to one picture for all three would fail here.
	assert.match(RAIL, /class="rail-icon ui-mode-icon ui-mode-\{uiMode\}"/);
	// And that interpolation can only ever be one of the three, so every value
	// it produces has a rule below.
	for (const mode of [...MODES, 'nonsense', null, undefined]) {
		assert.ok(MODES.includes(normalizeUiMode(mode)), String(mode));
	}
});

test('T-53  it is three bars, and each has a length of its own', () => {
	const bars = RAIL.match(/<span class="ui-mode-bar"><\/span>/g) ?? [];
	assert.equal(bars.length, 3);
	const widths = [...RAIL.matchAll(/\.ui-mode-bar:nth-child\(\d\) \{[^}]*width: (\d+)px/g)].map(
		(match) => Number(match[1])
	);
	assert.equal(widths.length, 3);
	// Falling, so the mark reads as an amount rather than as three of a thing.
	assert.deepEqual(widths, [...widths].sort((a, b) => b - a));
	assert.equal(new Set(widths).size, 3);
});

test('T-53  the three modes are not drawn the same', () => {
	// simple holds two bars back, custom one, full none. The control is `full`:
	// a rule that faded a bar in every mode would pass the first two checks.
	const faded = RAIL.match(/((?:\.ui-mode-\w+ \.ui-mode-bar:nth-child\(\d\),?\s*)+)\{ opacity: 0\.3; \}/);
	assert.ok(faded, 'no mode fades a bar');
	const selectors = faded[1];
	assert.match(selectors, /\.ui-mode-simple \.ui-mode-bar:nth-child\(2\)/);
	assert.match(selectors, /\.ui-mode-simple \.ui-mode-bar:nth-child\(3\)/);
	assert.match(selectors, /\.ui-mode-custom \.ui-mode-bar:nth-child\(3\)/);
	assert.doesNotMatch(selectors, /\.ui-mode-full /);
	// Which makes the three counts 1, 2 and 3 solid bars.
	const held = (mode: string) => (selectors.match(new RegExp(`\\.ui-mode-${mode} `, 'g')) ?? []).length;
	assert.deepEqual([3 - held('simple'), 3 - held('custom'), 3 - held('full')], [1, 2, 3]);
});

// ------------------------------------------------------------------- T-54

test('T-54  the frame that meant nothing, and the dot nobody could see, are gone', () => {
	// The old glyph drew its divider with a gradient stop and hung a 4x2 dot in
	// the corner. Neither survives; leaving them would draw both marks at once.
	assert.doesNotMatch(RAIL, /\.ui-mode-icon::before/);
	assert.doesNotMatch(RAIL, /\.ui-mode-icon::after/);
	assert.doesNotMatch(RAIL, /linear-gradient\(90deg, transparent 35%/);
	// The icons around it still use the pseudo-element idiom, so this is a
	// change to one mark and not to how the rail draws marks.
	assert.match(RAIL, /\.user-icon::before/);
	assert.match(RAIL, /\.gear-icon::before/);
});
