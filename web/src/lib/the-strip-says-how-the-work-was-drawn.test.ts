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
	assert.match(PANEL, /drawOptionRows\(statusHistoryItem\?\.draw_options/);
	assert.match(PANEL, /statusStage1ModelOnly/);
	assert.match(PANEL, /statusStage2ModelOnly/);
	assert.match(PANEL, /statusCatalogName/);
	assert.match(PANEL, /statusCanvasName/);
	assert.match(PANEL, /sketchStateShort\(statusSketchState, isJapanese\)/);
	assert.match(PANEL, /sketchStateNote\(statusSketchState, isJapanese\)/);
	assert.match(PANEL, /sketchStateShort\(statusSketchState, isJapanese\)\} \({option.text}\)/);
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
