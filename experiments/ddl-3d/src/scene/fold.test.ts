import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { buildScene, unpackMesh } from './build.ts';
import { FOLDED, foldedShare, smallestLayerGap } from './fold.ts';
import init, { prepare_scene } from '../../public/wasm/score_adapter.js';

await init({ module_or_path: readFileSync(new URL('../../public/wasm/score_adapter_bg.wasm', import.meta.url)) });
const solids = JSON.parse(readFileSync(new URL('../../fixtures/solids.json', import.meta.url), 'utf8'));

/** Each solid's span along z when folded at the front, in drawing order. */
function foldedSpans(instructions: unknown[]) {
  const value = structuredClone(solids); value.score.instructions = instructions;
  const result = JSON.parse(prepare_scene(JSON.stringify(value)));
  assert.equal(result.ok, true, result.error);
  const packet = buildScene(result), gap = smallestLayerGap(packet.meshes.map(mesh => mesh.layerZ));
  return packet.meshes.map(mesh => {
    const geometry = unpackMesh(mesh); geometry.computeBoundingBox();
    const { min, max } = geometry.boundingBox!; geometry.dispose();
    const share = mesh.depthPath ? 1 : foldedShare(max.z - min.z, gap);
    return { order: mesh.layerZ, low: mesh.layerZ + min.z * share, high: mesh.layerZ + max.z * share, line: !!mesh.depthPath };
  });
}

// Failure (swift's iPhone, 2026-11-20): a thick square drawn first hid the
// band and lines drawn after it, so the front of the solids was not the 2D picture.
test('folded at the front, a later solid is never behind an earlier one', () => {
  const band = { primitive: 'square', position: [0, 0.55], size: [1, 0.1], filled: true, color: 'blue', weight: 'rotring' };
  const many = Array.from({ length: 300 }, (_, i) => ({ primitive: 'circle', center: [0.1 + (i % 20) * 0.04, 0.1 + Math.floor(i / 20) * 0.05], radius: 0.015, filled: true, color: 'red', weight: 'rotring' }));
  const spans = foldedSpans([
    { primitive: 'square', position: [0, 0.2], size: [1, 0.618], filled: true, color: 'blue', weight: 'rotring' },
    band, ...many,
    { primitive: 'line', from: [0.1, 0.3], to: [0.9, 0.3], color: 'white', weight: 'rotring' },
  ]).filter(span => !span.line).sort((a, b) => a.order - b.order);
  assert.ok(spans.length > 300);
  for (let i = 1; i < spans.length; i++) {
    if (spans[i].order === spans[i - 1].order) continue;
    assert.ok(spans[i].low > spans[i - 1].high, `solid ${i} reaches behind the one drawn before it`);
  }
});

test('a folded solid keeps at most 0.2% of its thickness, and a quarter of the layer gap', () => {
  assert.equal(foldedShare(0.2, 1), FOLDED);
  assert.equal(foldedShare(1, 0.0002), 0.0001);
  assert.ok(Math.abs(foldedShare(0.5, 0.0016) - 0.0008) < 1e-12);
  assert.ok(Math.abs(smallestLayerGap([0.3, -0.1, 0.3, 0.2]) - 0.1) < 1e-12);
  assert.equal(smallestLayerGap([0]), Infinity);
});
