import test from 'node:test';
import assert from 'node:assert/strict';
import { glassLayerPlan } from './glassLayers.ts';

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
