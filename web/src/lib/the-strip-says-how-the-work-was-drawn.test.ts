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
import { drawOptionRows, INPUT_PANEL_ORDER } from './features/draw-options.ts';
import { ja } from './i18n/ja.ts';
import { sketchStateShort } from './sketch.ts';

const here = path.dirname(new URL(import.meta.url).pathname);
const read = (relative: string) => fs.readFileSync(path.join(here, relative), 'utf8');
const PANEL = read('./components/CanvasPanel.svelte');
const INPUT = read('./components/InputPanel.svelte');
const DRAW_CONDITIONS = read('./components/DrawConditions.svelte');
const ARTWORK = read('./features/canvas/CanvasArtworkWorkspace.svelte');
const PAGE = read('../routes/+page.svelte');

test('the saved-work strip retains sketch results and readable condition names', () => {
	// One source: the saved work on screen, else the result on screen.
	assert.match(PANEL, /stripOptions = \$derived\(statusHistoryItem\?\.draw_options \?\? result\?\.draw_options \?\? null\)/);
	assert.match(PANEL, /drawOptionRows\(stripOptions, t\(\), \{ image: stripIsImage, order: INPUT_PANEL_ORDER \}\)/);
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
	const row = PANEL.slice(PANEL.indexOf('<div class="right-tabs">'), PANEL.indexOf('{#snippet workActions()}'));
	// Tabs, then the conditions: one row in source order. The work's actions
	// stand over the canvas instead (the next test).
	const tabs = row.indexOf('class="rtab-group" role="tablist"');
	const strip = row.indexOf('<div class="render-meta-strip" role="group"');
	assert.ok(tabs >= 0 && tabs < strip, 'the row is not tabs, then conditions');
	assert.doesNotMatch(row, /<WorkActionMenu|work-action-save-first/);
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

test('the strip traces the input panel\'s conditions top to bottom, left to right (2026-11-05)', () => {
	assert.deepEqual([...INPUT_PANEL_ORDER], ['models', 'catalog', 'route', 'sketch', 'composition', 'wild', 'canvas_aspect']);
	// The input panel itself, top to bottom: model, catalog, the route and its
	// two stages, the stroke limit, the canvas.
	const conditions = INPUT.slice(INPUT.indexOf('{#snippet inputConditionRows()}'), INPUT.indexOf('{#snippet inputSettings()}'));
	const at = ['t().modelButton', 't().colorCatalogButton', '<DrawConditions', 't().wildButton', '<CanvasAspectPlugin']
		.map((token) => conditions.indexOf(token));
	assert.ok(at.every((index) => index >= 0), 'an input condition is missing from the panel');
	for (let i = 1; i < at.length; i += 1) assert.ok(at[i - 1] < at[i], `input condition ${i} moved`);
	const draw = DRAW_CONDITIONS.indexOf.bind(DRAW_CONDITIONS);
	const [route, sketch, composition] = ['onSelectRoute(option)', 'onSelectSketchMode(sketchOn', 'onSelectCompositionMode(compositionMode'].map(draw);
	assert.ok(route >= 0 && route < sketch && sketch < composition, 'the route and its two stages moved');
	// The rows come out in that order; a picture skips the three text-only ones.
	const keys = drawOptionRows(null, ja, { order: INPUT_PANEL_ORDER }).map((row) => row.key);
	assert.deepEqual(keys, [...INPUT_PANEL_ORDER]);
	assert.deepEqual(drawOptionRows(null, ja, { image: true, order: INPUT_PANEL_ORDER }).map((row) => row.key),
		['models', 'catalog', 'wild', 'canvas_aspect']);
});

test('the work\'s actions stand over the canvas\'s top right, on the Work tab (2026-11-05)', () => {
	const snippet = PANEL.slice(PANEL.indexOf('{#snippet workActions()}'), PANEL.indexOf('{#snippet modeControl()}'));
	assert.match(snippet, /<div class="canvas-work-actions">\s*<WorkActionMenu/);
	assert.match(snippet, /class="canvas-work-actions work-action-save-first" role="status"/);
	assert.equal((PANEL.match(/<WorkActionMenu/g) ?? []).length, 1, 'the menu stands in two places');
	// Only the Work tab's workspace renders it.
	assert.match(PANEL, /\{#if outputTab === 'canvas'\}\s*<CanvasArtworkWorkspace[^>]*?topRightControls=\{workActions\}/);
	assert.match(ARTWORK, /<div class="canvas-top-right" onpointerdown=\{\(event\) => event\.stopPropagation\(\)\}>\s*\{@render topRightControls\?\.\(\)\}/);
	assert.match(ARTWORK, /\.canvas-top-right \{ position: absolute; top: 12px; right: 12px; z-index: 14;/);
	// Opening lower than the tabs' row did, the menu scrolls inside the canvas
	// area instead of being cut off by it (488px against 466px at 1372x716).
	assert.match(PANEL, /container: canvas-area \/ size;/);
	assert.match(PANEL, /\.canvas-work-actions :global\(\.work-action-menu \.work-action-dropdown\) \{ max-height: calc\(100cqh - 64px\); overflow-y: auto; \}/);
	// It is a work tool: the simple view hides it with the rest.
	assert.match(PAGE, /\.ui-hide-work-tools :global\(\.canvas-work-actions\)/);
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
