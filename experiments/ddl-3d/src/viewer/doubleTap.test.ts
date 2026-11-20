import test from 'node:test';
import assert from 'node:assert/strict';
import { DoubleTap } from './doubleTap.ts';

test('two taps close in time and place make a double tap; a third starts again', () => {
  const taps = new DoubleTap();
  assert.equal(taps.tap(0, 100, 100), false);
  assert.equal(taps.tap(300, 120, 110), true);
  assert.equal(taps.tap(400, 120, 110), false);
});

test('taps too far apart in time or place are single taps', () => {
  const taps = new DoubleTap();
  assert.equal(taps.tap(0, 100, 100), false);
  assert.equal(taps.tap(500, 100, 100), false);
  assert.equal(taps.tap(700, 200, 100), false);
});
