// Run with: npm run test:unit  (node:test, no test dependency)
//
// The strip above the canvas names how the work on screen was drawn and what
// its sketch did, between the canvas and the size (the author, 2026-10-26).
// Both were said only in the drawer and in the input chips, which show the
// next drawing, not the one on screen.
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import { test } from 'node:test';

import { workRouteLabel } from './draw-route.ts';
import { sketchStateShort } from './sketch.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const PANEL = fs.readFileSync(path.join(here, './components/CanvasPanel.svelte'), 'utf8');

test('the saved-work strip retains sketch results and readable condition names', () => {
	// One source: the saved work on screen, else the result on screen.
	assert.match(PANEL, /stripOptions = \$derived\(statusHistoryItem\?\.draw_options \?\? result\?\.draw_options \?\? null\)/);
	assert.match(PANEL, /drawOptionRows\(stripOptions, t\(\), \{ image: stripIsImage \}\)/);
	assert.match(PANEL, /statusStage1ModelOnly/);
	assert.match(PANEL, /statusStage2ModelOnly/);
	assert.match(PANEL, /t\(\)\.drawOptionsStage1Short/);
	assert.match(PANEL, /t\(\)\.drawOptionsStage2Short/);
	// The model lines keep their layout (they ran together without it).
	assert.match(PANEL, /\.render-meta-model-line \{ display: flex/);
	assert.match(PANEL, /statusCatalogName/);
	assert.match(PANEL, /statusCanvasName/);
	assert.match(PANEL, /sketchStateShort\(statusSketchState, isJapanese\)/);
	assert.match(PANEL, /sketchStateNote\(statusSketchState, isJapanese\)/);
	assert.match(PANEL, /sketchStateShort\(statusSketchState, isJapanese\)\} \({option.text}\)/);
});

test('the strip shares the tabs\' row, and only the tabs look pressable (2026-11-05)', () => {
	const row = PANEL.slice(PANEL.indexOf('<div class="right-tabs">'), PANEL.indexOf('{#snippet modeControl()}'));
	// Tabs, then the work's actions, then the conditions: one row in source order.
	const tabs = row.indexOf('class="rtab-group" role="tablist"');
	const actions = row.indexOf('<WorkActionMenu');
	const strip = row.indexOf('<div class="render-meta-strip" role="group"');
	assert.ok(tabs >= 0 && tabs < actions && actions < strip, 'the row is not tabs, actions, conditions');
	assert.equal((row.match(/role="tab" aria-selected=/g) ?? []).length, 2);
	const css = (selector: string) => {
		const at = PANEL.indexOf(`\t${selector} {`);
		assert.ok(at >= 0, `${selector} has no rule`);
		return PANEL.slice(at, PANEL.indexOf('}', at));
	};
	// Outside the narrow query the strip takes the rest of the row, not a row of its own.
	assert.match(css('.render-meta-strip'), /flex: 1 1 0;/);
	assert.match(css('.render-meta-strip'), /cursor: default;/);
	assert.doesNotMatch(css('.render-meta-strip'), /background|border-radius/);
	assert.doesNotMatch(PANEL, /\.render-meta-(?:strip|item)[^{]*:hover/);
	// The tabs carry the input panel's accent underline and a hover fill.
	assert.match(PANEL, /\.rtab\.active \{ border-bottom-color: var\(--accent\);/);
	assert.match(PANEL, /\.rtab:hover:not\(\.active\):not\(:disabled\) \{[^}]*background: var\(--bg2\)/);
});

test('while a drawing runs, the strip keeps naming the work whose picture is on the canvas', () => {
	const PAGE = fs.readFileSync(path.join(here, '../routes/+page.svelte'), 'utf8');
	// Held only while the same result is on screen; a new result replaces it.
	assert.match(PAGE, /if \(item\) heldStatus = \{ item, result: work\.result \}/);
	assert.match(PAGE, /liveStatusHistoryItem\s*\?\? \(heldStatus && work\.result && heldStatus\.result === work\.result \? heldStatus\.item : null\)/);
	// A just-saved result whose generation is not read yet is not called standalone.
	assert.match(PANEL, /statusGenerationPending = \$derived\(!statusHistoryItem && !!result\?\.history_id\)/);
	assert.match(PANEL, /: statusGenerationPending \? '…'/);
	// The creation time reads the same work, not only the selected one.
	assert.match(PAGE, /const at = statusHistoryItem\?\.at \?\? work\.result\?\.history_at \?\? null;/);
});

test('the route names the work on screen, a picture going through neither', () => {
	assert.equal(workRouteLabel({ description_ddl: { reading_state: 'read' } }, true), '言葉で描く');
	assert.equal(workRouteLabel({}, true), '型で描く');
	assert.equal(workRouteLabel({ image_ddl: { review: true } }, true), '画像から書く');
	assert.equal(workRouteLabel(null, false), 'With a plan');
});

test('the sketch says what it did, and a missing record is not Off', () => {
	// The words follow the input's switch (2026-10-27): 通した／通さない.
	assert.equal(sketchStateShort('fine', true), '通した');
	assert.equal(sketchStateShort('supplemented', true), '通した');
	assert.equal(sketchStateShort('not_needed', true), '通した（補いなし）');
	assert.equal(sketchStateShort('fallback', true), '届かず');
	assert.equal(sketchStateShort('off', true), '通さない');
	assert.equal(sketchStateShort(null, true), '記録なし');
	assert.notEqual(sketchStateShort(null, false), sketchStateShort('off', false));
});
