import test from 'node:test';
import assert from 'node:assert/strict';
import { paintInTurn, paintOrder } from '../viewer/paintQueue.ts';

// Failure: one failed decode stops every other mark, or more than four decode at once.
test('paint runs four at a time in the given order and continues past a failure', async () => {
  const started: number[] = [];
  let running = 0, most = 0;
  const failures = await paintInTurn([0, 1, 2, 3, 4, 5, 6, 7, 8, 9], 4, async item => {
    started.push(item); running++; most = Math.max(most, running);
    await new Promise(resolve => setTimeout(resolve, item * 7 % 5));
    running--;
    if (item === 2) throw new Error('circle_appearance_timeout');
  });
  assert.deepEqual(started, [0, 1, 2, 3, 4, 5, 6, 7, 8, 9]);
  assert.equal(most, 4);
  assert.deepEqual(failures.map(({ item, error }) => [item, (error as Error).message]), [[2, 'circle_appearance_timeout']]);
});

// Failure: marks are painted in packet order, leaving the front layer for last.
test('paint starts at the front layer and keeps the order within a layer', () => {
  const marks = [{ id: 'a', layerZ: -0.2 }, { id: 'b', layerZ: 0.4 }, { id: 'c', layerZ: 0 }, { id: 'd', layerZ: 0.4 }, { id: 'e', layerZ: -0.2 }];
  assert.deepEqual(paintOrder(marks, mark => mark.layerZ).map(mark => mark.id), ['b', 'd', 'c', 'a', 'e']);
});
