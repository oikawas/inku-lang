// Run with: npm run test:unit  (node:test, no test dependency)
//
// While a batch runs, the tab that says 「バッチ」 also carries a counter, and the
// counter reserves its widest form so the word beside it does not shuffle as the
// digits cross a boundary. That reserve is taken out of a tab which is a third
// of the row, and what was left was not enough for the word: it broke between
// its characters and the tab grew a line, which moved everything below it.
//
// Measured in the running page at a 1235px window, before the fix:
//   (3/12)        tab 38px, word on one line
//   (12/12 ↻2)    tab 46px, word on two lines
//   (120/120 ↻2)  tab 58px, word on three lines
//
// Both strings are one line each by rule now. This is a CSS fact, so it is
// asserted against the stylesheet: neither `npm run check` nor a render test
// would catch the word coming back onto two lines.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

const PANEL = readFileSync(new URL('./components/InputPanel.svelte', import.meta.url), 'utf-8');

/** The body of one CSS rule, so a `nowrap` belonging to a neighbour cannot
 *  satisfy an assertion about this one. */
function ruleBody(selector: string): string {
	const start = PANEL.indexOf(`\n\t${selector} {`);
	const oneLine = PANEL.indexOf(`\n\t${selector} { `);
	if (oneLine !== -1 && (start === -1 || oneLine <= start)) {
		return PANEL.slice(oneLine, PANEL.indexOf('}', oneLine) + 1);
	}
	assert.notEqual(start, -1, `no rule for ${selector}`);
	return PANEL.slice(start, PANEL.indexOf('}', start) + 1);
}

test('T-159  the word on the batch tab cannot break across lines', () => {
	assert.match(ruleBody('.tab-label'), /white-space:\s*nowrap/);
});

test('T-160  the counter beside it cannot break either', () => {
	// "(12/12 ↻2)" carries a space, which is a break opportunity of its own.
	assert.match(ruleBody('.tab-progress'), /white-space:\s*nowrap/);
});

test('T-161  the counter is still reserved at its widest, which is why the room is tight', () => {
	// The reserve is the reason the word had too little room. If it were dropped
	// the wrap would go away for the wrong reason -- and the word would start
	// shuffling sideways on every digit boundary instead.
	assert.match(PANEL, /min-width:\s*\{batchProgressWidth\}ch/);
	assert.match(PANEL, /2 \* String\(batchTotal\)\.length \+ 3/);
});
