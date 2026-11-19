import test from 'node:test';
import assert from 'node:assert/strict';
import { validState } from './protocol.ts';

const base = { position: [0, 0, 20], target: [0, 0, 0], zoom: 1, projection: 'orthographic', depth: 1, orthoHeight: 2 };
const glass = { angle: 1, leaf: 0.6, light: 0, glassColor: 'none', frictionless: true };

test('a view state may name its view and carry the glass settings in their ranges', () => {
  assert.equal(validState(base), true);
  assert.equal(validState({ ...base, viewMode: 'solids' }), true);
  assert.equal(validState({ ...base, viewMode: 'glass', glass }), true);
  assert.equal(validState({ ...base, viewMode: 'glass', glass: { ...glass, angle: 2, leaf: 0, light: -1, glassColor: 'layers', frictionless: false } }), true);
});

test('an unknown view or a glass setting out of its range is refused', () => {
  assert.equal(validState({ ...base, viewMode: 'mirror' }), false);
  for (const change of [{ angle: 2.01 }, { leaf: -0.1 }, { light: 1.5 }, { light: Number.NaN }, { glassColor: 'red' }, { frictionless: 1 }]) {
    assert.equal(validState({ ...base, viewMode: 'glass', glass: { ...glass, ...change } }), false, JSON.stringify(change));
  }
  const { angle: _angle, ...missing } = glass;
  assert.equal(validState({ ...base, glass: missing }), false);
});
