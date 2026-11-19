import test from 'node:test';
import assert from 'node:assert/strict';
import { fanGeometry, glassLayerPlan, planeZ } from './glassLayers.ts';

// Failure: layers cross inside the paper, so the front view's overlap order
// differs from 2D. Every later layer stays at or in front of the one before,
// at the paper's corners and along the axis, at the ends of both controls.
test('fan layers never cross inside the paper', () => {
  for (const canvas of [[1, 1], [1.5, 1], [1, 1.5]] as [number, number][]) {
    for (const count of [1, 2, 5, 8]) for (const angle of [0, 1, 2]) for (const spacing of [0, 3]) {
      const fan = fanGeometry(count, canvas, { angle, spacing, front: 0.03, backTilt: 0 });
      for (const x of [-canvas[0] / 2, 0, canvas[0] / 2]) {
        for (let i = 1; i < count; i++) {
          assert.ok(planeZ(fan.planes[i], fan.axisX, x) >= planeZ(fan.planes[i - 1], fan.axisX, x) - 1e-12);
        }
        for (const plane of fan.planes) {
          const z = planeZ(plane, fan.axisX, x);
          assert.ok(z < fan.front && z > fan.backOffset - (x - fan.axisX) * fan.backTan);
        }
      }
      if (count === 1) assert.ok(Math.abs(Math.atan(fan.planes[0].tan) - angle * 12 * Math.PI / 180) < 1e-12);
    }
  }
});

// Failure: another chunk's marks share a glass layer, or a chunk named again
// after another one loses the 2D order.
test('layers follow chunks in paint order, then instructions, at most eight', () => {
  const plan = glassLayerPlan([0, 1, 2, 3, 4], ['水面', '光', null, '光', '光']);
  assert.deepEqual([...plan.layerOf], [[0, 0], [1, 1], [2, 2], [3, 3], [4, 3]]);
  assert.deepEqual(plan.names, ['水面', '光', null, '光']);
  const single = glassLayerPlan([0, 1, 2], ['点', '点', '点']);
  assert.equal(single.source, 'instructions');
  assert.equal(single.names.length, 3);
  const many = glassLayerPlan(Array.from({ length: 20 }, (_, i) => i), null);
  assert.equal(many.names.length, 8);
  assert.deepEqual([...new Set(many.layerOf.values())], [0, 1, 2, 3, 4, 5, 6, 7]);
  assert.ok([...many.layerOf].every(([index, layer], k, all) => k === 0 || layer >= all[k - 1][1] || index < all[k - 1][0]));
});
