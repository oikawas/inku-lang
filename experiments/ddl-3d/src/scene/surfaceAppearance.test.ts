import test from 'node:test';
import assert from 'node:assert/strict';
import { BoxGeometry } from 'three';
import { mapPaintSurfaces, sidePaintPixels } from '../viewer/circleAppearance.ts';
import { assignLayers } from './layers.ts';
import type { MeshPacket } from './types.ts';

// Failure: extruded walls have constant canvas UVs and sample a blank stripe.
test('box walls unfold their thickness through the filtered paint', () => {
  const source = new BoxGeometry(0.2, 0.2, 0.2);
  const geometry = mapPaintSurfaces(source, [0.35, 0.35, 0.3, 0.3], [1, 1], true);
  const position = geometry.getAttribute('position'), uv = geometry.getAttribute('uv');
  assert.equal(uv.count, position.count);
  assert.ok(geometry.groups.some(group => group.materialIndex === 0));
  assert.ok(geometry.groups.some(group => group.materialIndex === 1));
  const wall = geometry.groups.find(group => group.materialIndex === 1)!;
  const values = Array.from({ length: wall.count }, (_, i) => uv.getX(wall.start + i));
  assert.ok(Math.max(...values) - Math.min(...values) > 0.5);
  assert.ok(Array.from(uv.array).every(Number.isFinite));
  source.dispose(); geometry.dispose();
});

// Failure: transparent SVG padding becomes a white band instead of pigment.
test('solid side paint keeps object pigment and filtered opacity as texture', () => {
  const pixels = new Uint8ClampedArray([255, 255, 255, 0, 51, 102, 153, 128, 51, 102, 153, 255]);
  const original = pixels.slice(), result = sidePaintPixels(pixels, '#336699');
  assert.deepEqual(Array.from(result.slice(0, 4)), [31, 61, 92, 255]);
  assert.deepEqual(Array.from(result.slice(8)), [51, 102, 153, 255]);
  assert.ok(result[4] > result[0] && result[4] < result[8]);
  assert.deepEqual(pixels, original);
});

const mesh = (performedIndex: number, sourceIndex = 0): MeshPacket => ({
  positions: new Float32Array(), normals: new Float32Array(), indices: null,
  color: '#336699', opacity: 1, sourceIndex, performedIndex, instanceIndex: 0,
  primitive: 'line', role: 'object', layerIndex: 0, layerZ: 0,
});

// Failure: lines in a layer share Z, or a dense layer crosses its neighbours.
test('later objects recede within a bounded source layer', () => {
  const objects = Array.from({ length: 100 }, (_, i) => mesh(i));
  objects.push(mesh(100, 1));
  assert.equal(assignLayers(objects, [1, 1]), 2);
  assert.ok(objects.slice(1, 100).every((m, i) => m.layerZ < objects[i].layerZ));
  assert.ok(objects[0].layerZ - objects[99].layerZ <= 0.020000001);
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
