import test from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry, SphereGeometry } from 'three';
import { extendColor, mapPaintSurfaces } from '../viewer/circleAppearance.ts';
import { assignLayers } from './layers.ts';
import type { MeshPacket } from './types.ts';

// Failure (2026-11-20): walls sampled the paint by depth, a column unrelated
// to their edge, so every cube and sphere showed a seam where face met face.
test('a wall folds the paint in from its edge, meeting the cap at both edges', () => {
  const source = new BoxGeometry(0.2, 0.2, 0.2, 1, 1, 2);
  const options = { walls: true, round: false, filled: true, texel: 0 };
  const geometry = mapPaintSurfaces(source, [0.35, 0.35, 0.3, 0.3], [1, 1], options);
  const position = geometry.getAttribute('position'), uv = geometry.getAttribute('uv'), surf = geometry.getAttribute('surf');
  const cap = (x: number, y: number) => [(x + 0.5 - 0.35) / 0.3, 1 - (0.5 - y - 0.35) / 0.3];
  let edges = 0, middles = 0;
  for (let i = 0; i < position.count; i++) {
    if (surf.getX(i) !== 1) continue;
    const z = position.getZ(i), [u, v] = cap(position.getX(i), position.getY(i));
    if (Math.abs(Math.abs(z) - 0.1) < 1e-6) {
      edges++; assert.ok(Math.abs(uv.getX(i) - u) < 1e-6 && Math.abs(uv.getY(i) - v) < 1e-6, 'an edge samples the cap texel');
    } else if (Math.abs(z) < 1e-6) {
      // Half the thickness in from the edge: 0.1 of 0.3 in u or v.
      middles++; assert.ok(Math.abs(Math.hypot(uv.getX(i) - u, uv.getY(i) - v) - 0.1 / 0.3) < 1e-6, 'the middle reaches in by half the thickness');
    }
  }
  assert.ok(edges > 0 && middles > 0);
  assert.ok(Array.from(uv.array).every(Number.isFinite));
  assert.equal(geometry.groups.length, 0);
  source.dispose(); geometry.dispose();
});

// Failure (2026-11-20): a sphere switched material at 30 degrees of latitude,
// a crease that was seen from every side.
test('a filled sphere is one surface that knows its height; an outline is not blended', () => {
  const source = new SphereGeometry(0.12, 32, 16);
  const geometry = mapPaintSurfaces(source, [0.35, 0.35, 0.3, 0.3], [1, 1], { walls: true, round: true, filled: true, texel: 0 });
  const surf = geometry.getAttribute('surf'), position = geometry.getAttribute('position');
  for (let i = 0; i < surf.count; i++) {
    assert.equal(surf.getX(i), 0);
    assert.ok(Math.abs(surf.getY(i) - position.getZ(i) / 0.12) < 1e-6);
  }
  const outline = mapPaintSurfaces(source, [0.35, 0.35, 0.3, 0.3], [1, 1], { walls: false, round: true, filled: false, texel: 0 });
  assert.ok(Array.from({ length: outline.getAttribute('surf').count }, (_, i) => outline.getAttribute('surf').getY(i)).every(y => y === 2));
  source.dispose(); geometry.dispose(); outline.dispose();
});

// Failure: transparent SVG padding became a white band instead of pigment.
test('the paint colour spreads into its transparent pixels, keeping alpha', () => {
  // 4 x 2: one blue pixel at the top left, the rest transparent white.
  const data = new Uint8ClampedArray(4 * 2 * 4);
  for (let i = 0; i < 8; i++) data.set([255, 255, 255, 0], i * 4);
  data.set([0, 0, 255, 255], 0);
  const original = data.slice(), { filled, blur } = extendColor(data, 4, 2, '#ff0000');
  // Rows run bottom to top: the blue pixel is in the second row.
  assert.deepEqual(Array.from(filled.slice(16, 20)), [0, 0, 255, 255]);
  for (let i = 0; i < 8; i++) {
    if (i === 4) continue;
    assert.deepEqual(Array.from(filled.slice(i * 4, i * 4 + 4)), [0, 0, 255, 0], `pixel ${i}`);
  }
  assert.ok(blur.width <= 16 && blur.height <= 16 && blur.data.every((v, i) => i % 4 !== 3 || v === 255));
  assert.deepEqual(data, original);
  const empty = extendColor(new Uint8ClampedArray(16), 2, 2, '#336699');
  assert.deepEqual(Array.from(empty.filled.slice(0, 4)), [0x33, 0x66, 0x99, 0]);
});

const mesh = (performedIndex: number, sourceIndex = 0): MeshPacket => ({
  positions: new Float32Array(), normals: new Float32Array(), indices: null,
  color: '#336699', opacity: 1, sourceIndex, performedIndex, instanceIndex: 0,
  primitive: 'line', role: 'object', layerIndex: 0, layerZ: 0,
});

// Failure: copies still occupy an imperceptibly thin plane.
test('individual objects share the full range without crossing source layers', () => {
  const objects = Array.from({ length: 100 }, (_, i) => mesh(i));
  objects.push(mesh(100, 1));
  assert.equal(assignLayers(objects, [1, 1]), 2);
  assert.ok(objects.slice(1, 100).every((m, i) => m.layerZ < objects[i].layerZ));
  assert.ok(objects[0].layerZ - objects[99].layerZ > 0.79);
  assert.ok(objects[100].layerZ > objects[0].layerZ);
  assert.equal(objects[100].layerZ, 0.4);
});

// Failure: staggering separates a closed pair's two arcs from its interior.
test('a closed pair moves as one object while an independent line recedes', () => {
  const first = mesh(0), fill = { ...mesh(0), role: 'pair-fill' as const,
    relatedSourceIndex: 1, relatedPerformedIndex: 1, relatedInstanceIndex: 0 };
  const second = mesh(1, 1), next = mesh(2);
  assert.equal(assignLayers([first, fill, second, next], [1, 1]), 1);
  assert.equal(first.layerZ, fill.layerZ); assert.equal(second.layerZ, fill.layerZ);
  assert.ok(next.layerZ < first.layerZ);
});
