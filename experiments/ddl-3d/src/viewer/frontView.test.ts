import test from 'node:test';
import assert from 'node:assert/strict';
import { OrthographicCamera, Vector3 } from 'three';
import { frontView } from './frontView.ts';

// Failure: the front object changes pixel size/position when switching from 2D.
test('front projection preserves 2D pixels and pan at every layer depth', () => {
  const view = frontView([1.4, 1], 1200, 800, { pixelWidth: 840, pixelHeight: 600, panX: 42, panY: -24, zoom: 1.5 });
  const camera = new OrthographicCamera(-view.height * 0.75, view.height * 0.75, view.height / 2, -view.height / 2, 0.01, 100);
  camera.position.set(view.target[0], view.target[1], 10); camera.lookAt(...view.target); camera.updateMatrixWorld();
  const pixel = (x: number, y: number, z: number) => {
    const point = new Vector3(x, y, z).project(camera);
    return [(point.x + 1) * 600, (1 - point.y) * 400];
  };
  for (const z of [-0.4, 0, 0.7]) {
    const left = pixel(0.2, -0.1, z), right = pixel(0.4, -0.1, z);
    assert.ok(Math.abs(right[0] - left[0] - 120) < 1e-8);
    assert.ok(Math.abs(left[0] - (600 + 120 + 42)) < 1e-8);
    assert.ok(Math.abs(left[1] - (400 + 60 - 24)) < 1e-8);
  }
  assert.equal(view.referenceHeight / view.height, 1.5);
});
