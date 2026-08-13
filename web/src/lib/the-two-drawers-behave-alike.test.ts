// Run with: npm run test:unit  (node:test, no test dependency)
//
// The app has two drawers that slide in over the canvas from the right: the
// saijiki and the provenance panel. They behaved differently for no reason the
// author could see -- one closed when you pressed outside it and the other did
// not, one slid in and the other appeared whole.
//
// T-44 (the saijiki closes on a press outside, and its own button still
// toggles it).
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');
const SAIJIKI = read('./components/SaijikiDrawer.svelte');
const PANEL = read('./components/CanvasPanel.svelte');

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
