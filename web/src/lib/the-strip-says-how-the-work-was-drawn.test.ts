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

test('the route and the sketch stand between the canvas and the size', () => {
	const at = (item: string) => PANEL.indexOf(`class="render-meta-item ${item}"`);
	const [canvas, route, sketch, size] = ['render-meta-canvas', 'render-meta-route', 'render-meta-sketch', 'render-meta-svg-size'].map(at);
	assert.ok(canvas > 0 && route > 0 && sketch > 0 && size > 0, 'an item is missing from the strip');
	assert.ok(canvas < route && route < sketch && sketch < size, 'the order is canvas, route, sketch, size');
});

test('the route names the work on screen, a picture going through neither', () => {
	assert.equal(workRouteLabel({ description_ddl: { reading_state: 'read' } }, true), '読んで描く');
	assert.equal(workRouteLabel({}, true), '今の流れ');
	assert.equal(workRouteLabel({ image_ddl: { review: true } }, true), '画像から書く');
	assert.equal(workRouteLabel(null, false), 'Current stages');
});

test('the sketch says what it did, and a missing record is not Off', () => {
	assert.equal(sketchStateShort('fine', true), 'あり');
	assert.equal(sketchStateShort('supplemented', true), 'あり');
	assert.equal(sketchStateShort('not_needed', true), 'あり（補いなし）');
	assert.equal(sketchStateShort('fallback', true), '届かず');
	assert.equal(sketchStateShort('off', true), 'なし');
	assert.equal(sketchStateShort(null, true), '記録なし');
	assert.notEqual(sketchStateShort(null, false), sketchStateShort('off', false));
});
