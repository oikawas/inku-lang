// Run with: npm run test:unit  (node:test, no test dependency)
//
// T-26: the graphic shown on an empty canvas does not take the canvas
// proportion. The frame follows the chosen aspect; the shapes inside it must
// not, or a circle stops being a circle. Measured at Pillar (1:5), where the
// triangle was a needle and the square a sliver.
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { test } from 'node:test';

import {
	PLACEHOLDER_MOTIF,
	placeholderMotifPlacement,
	placeholderMotifTransform
} from './canvas-placeholder.ts';

const read = (path: string) => readFileSync(new URL(path, import.meta.url), 'utf8');

/** The frame the panel builds: the shorter side is always PLACEHOLDER_MOTIF. */
function frame(aspectWidth: number, aspectHeight: number): [number, number] {
	const unit = Math.min(aspectWidth, aspectHeight);
	return [
		Math.round(PLACEHOLDER_MOTIF * (aspectWidth / unit)),
		Math.round(PLACEHOLDER_MOTIF * (aspectHeight / unit))
	];
}

// The nine canvas aspects the plugin offers, by their declared ratios.
const ASPECTS: [string, number, number][] = [
	['square', 1, 1],
	['golden', 1.618, 1],
	['a4', 1, 1.414],
	['b4', 1, 1.414],
	['pillar', 1, 5],
	['oban', 2, 3],
	['wide', 2.35, 1],
	['byobu', 2.2, 1],
	['vertical', 9, 16]
];

test('T-26: one scale, not one per axis, at every canvas aspect', () => {
	for (const [name, w, h] of ASPECTS) {
		const [width, height] = frame(w, h);
		const placement = placeholderMotifPlacement(width, height);
		// A single number is the whole claim: with two, the shapes stretch.
		assert.equal(typeof placement.scale, 'number', name);
		assert.ok(placement.scale > 0, name);
		// The transform must not spell a second factor -- `scale(a b)` is the
		// shape of the defect, and it is legal SVG that nothing else catches.
		const transform = placeholderMotifTransform(width, height);
		assert.match(transform, /scale\(-?[\d.]+\)$/, `${name}: ${transform}`);
	}
});

test('T-26: the motif fills the shorter side, whichever side that is', () => {
	// Tall and wide are not symmetric in the code -- one is width, the other
	// height -- so both directions are measured.
	const tall = placeholderMotifPlacement(...frame(1, 5));
	const wide = placeholderMotifPlacement(...frame(2.35, 1));
	assert.equal(tall.scale, 1);
	assert.equal(wide.scale, 1);
	// Centred on the long axis, untouched on the short one.
	assert.equal(tall.offsetX, 0);
	assert.equal(tall.offsetY, (5000 - 1000) / 2);
	assert.equal(wide.offsetY, 0);
	assert.equal(wide.offsetX, (2350 - 1000) / 2);
});

test('T-26: a square canvas moves nothing', () => {
	const square = placeholderMotifPlacement(...frame(1, 1));
	assert.deepEqual(square, { scale: 1, offsetX: 0, offsetY: 0 });
});

test('T-26: the motif is the same shape at every aspect', () => {
	// The centre of the motif box lands on the centre of the frame. If it did
	// not, a shape drawn at a fixed coordinate would appear to move as the
	// canvas changed, which reads as distortion even when nothing stretched.
	for (const [name, w, h] of ASPECTS) {
		const [width, height] = frame(w, h);
		const { scale, offsetX, offsetY } = placeholderMotifPlacement(width, height);
		const centreX = offsetX + (PLACEHOLDER_MOTIF * scale) / 2;
		const centreY = offsetY + (PLACEHOLDER_MOTIF * scale) / 2;
		assert.equal(centreX, width / 2, name);
		assert.equal(centreY, height / 2, name);
	}
});

test('T-26: no shape in the motif is written against the frame', () => {
	const panel = read('./components/CanvasPanel.svelte');
	const start = panel.indexOf('<g opacity="0.72"');
	assert.ok(start > 0, 'the motif group is missing');
	const motif = panel.slice(start, panel.indexOf('</g>', start));

	// The defect, exactly: a coordinate scaled by the frame's own dimensions.
	assert.doesNotMatch(motif, /placeholderWidth/);
	assert.doesNotMatch(motif, /placeholderHeight/);
	// It is placed by the one transform instead.
	assert.match(motif, /transform=\{placeholderTransform\}/);

	// The paper behind it still spans the whole frame: only the shapes are
	// square, and a background that stopped filling would be a new defect.
	const paper = panel.slice(panel.indexOf('<rect x="0" y="0"'), start);
	assert.match(paper, /width=\{placeholderWidth\}/);
	assert.match(paper, /height=\{placeholderHeight\}/);
});

// --- the motif itself (author's choice, 2026-08-17): mountain, water, moon ---

test('T-168  the motif is three strokes, and the moon is a circle', () => {
	const panel = read('./components/CanvasPanel.svelte');
	const start = panel.indexOf('<g opacity="0.72"');
	const motif = panel.slice(start, panel.indexOf('</g>', start));

	// Three, which is what was asked for: the ridge, the water, the moon. A
	// fourth would not be caught by anything above -- T-26 measures how the
	// motif is placed, not what is in it.
	const strokes = motif.match(/<(path|circle|rect|ellipse|line|polyline|polygon)\b/g) ?? [];
	assert.equal(strokes.length, 3, `motif has ${strokes.length} strokes: ${strokes}`);

	// The moon is a circle and not an ellipse. An ellipse is how a round thing
	// gets quietly squashed by hand, which is the defect this whole file exists
	// for -- reached by a different road than writing coordinates against the
	// frame, and so not covered by the check above.
	assert.match(motif, /<circle\b/);
	assert.doesNotMatch(motif, /<ellipse\b/);

	// Two open strokes and no filled shape: the picture is drawn, not blocked in.
	assert.equal((motif.match(/fill="none"/g) ?? []).length, 3);
});
