import { test } from 'node:test';
import assert from 'node:assert/strict';
import { adaptResolution, decay, FULL_RESOLUTION, frontWeight, releaseVelocity, snapsToFront, stopped, turnBetween } from './motion.ts';

const DEG = Math.PI / 180;
const close = (a: number, b: number, e = 1e-9) => assert.ok(Math.abs(a - b) < e, `${a} != ${b}`);

// The glass's release, as it was before the motion was shared (2026-11-20).
test('the release speed is the last 0.1 seconds of the drag', () => {
  const v = releaseVelocity([{ t: 0, az: 0, po: 0 }, { t: 900, az: 1, po: 0 }, { t: 950, az: 1 + 3 * DEG, po: 0 }, { t: 1000, az: 1 + 6 * DEG, po: 1 * DEG }], 1000)!;
  close(v.az, 6 * DEG / 0.1); close(v.po, 1 * DEG / 0.1);
});
test('a slow or single-sample release stays still', () => {
  assert.equal(releaseVelocity([{ t: 0, az: 0, po: 0 }, { t: 100, az: 1.9 * DEG, po: 0 }], 100), null);
  assert.equal(releaseVelocity([{ t: 100, az: 0, po: 0 }], 100), null);
  assert.equal(releaseVelocity([{ t: 0, az: 0, po: 0 }, { t: 50, az: 1, po: 0 }], 200), null);
});
test('a fast release is capped at 180 degrees a second, keeping its direction', () => {
  const v = releaseVelocity([{ t: 0, az: 0, po: 0 }, { t: 100, az: -60 * DEG, po: 80 * DEG }], 100)!;
  close(Math.hypot(v.az, v.po), 180 * DEG); close(v.az / v.po, -60 / 80);
});
test('a drag across the back keeps its direction', () => {
  const v = releaseVelocity([{ t: 0, az: 178 * DEG, po: 0 }, { t: 50, az: -179 * DEG, po: 0 }, { t: 100, az: -176 * DEG, po: 0 }], 100)!;
  close(v.az, 6 * DEG / 0.1);
  close(turnBetween(179 * DEG, -179 * DEG), 2 * DEG);
});
test('without friction it keeps its speed; with friction it halves in about 0.35 seconds', () => {
  assert.equal(decay(0.016, true), 1);
  close(decay(0.5, false), Math.exp(-1));
  assert.ok(Math.abs(decay(0.3466, false) - 0.5) < 1e-3);
  assert.equal(stopped({ az: 2 * DEG, po: 0 }, false), false);
  assert.equal(stopped({ az: 1.4 * DEG, po: 0 }, false), true);
  assert.equal(stopped({ az: 1.4 * DEG, po: 0 }, true), false);
});
test('a stop within 3 degrees of the front settles onto it', () => {
  assert.equal(snapsToFront(2.9 * DEG), true);
  assert.equal(snapsToFront(3.1 * DEG), false);
  assert.equal(snapsToFront(0), false);
});
test('the resolution steps down when heavy, back up when light, and is full when still', () => {
  let r = adaptResolution(FULL_RESOLUTION, 30, true, 0);
  assert.equal(r.value, 0.75);
  r = adaptResolution(r, 30, true, 100); assert.equal(r.value, 0.6);
  r = adaptResolution(r, 30, true, 200); assert.equal(r.value, 0.6);
  r = adaptResolution(r, 10, true, 300); assert.equal(r.value, 0.75);
  // Heavy right after the raise: down, and that raise waits 5 seconds.
  r = adaptResolution(r, 30, true, 400); assert.equal(r.value, 0.6);
  assert.equal(adaptResolution(r, 10, true, 5300).value, 0.6);
  assert.equal(adaptResolution(r, 10, true, 5500).value, 0.75);
  assert.equal(adaptResolution(r, null, false, 600).value, 1);
});
test('the front weight is 0 at the front and 1 once turned', () => {
  assert.equal(frontWeight(0, 2, 12), 0);
  assert.equal(frontWeight(2 * DEG, 2, 12), 0);
  close(frontWeight(7 * DEG, 2, 12), 0.5);
  assert.equal(frontWeight(30 * DEG, 2, 12), 1);
});
