import test from 'node:test';
import assert from 'node:assert/strict';
import { paintedRadii, rasterSizedSvg } from '../viewer/circleAppearance.ts';
import { buildScene } from './build.ts';
import type { PreparedScene } from './types.ts';

// Failure: an alpha-painted outline still receives the old extra globe bands.
test('outlined round appearance uses the same sphere volume as a filled round', () => {
  const input: PreparedScene = { ok: true, inputDigest: '', schemaDigest: '', mappingVersion: '', engineVersion: 1,
    scene: { canvas: [1, 1], background: '#ffffff', ground: false, diagnostics: [], recoveries: [], marks: [{
      sourceIndex: 0, performedIndex: 0, instanceIndex: 0, primitive: 'circle',
      shape: { kind: 'round', center: [0.5, 0.5], radii: [0.12, 0.12] }, transform: [1, 0, 0, 1, 0, 0],
      color: '#333333', width: 0.002, filled: false, opacity: 1, dash: [], weight: 'rotring', clips: [],
      appearance: { svg: '<svg/>', bounds: [0.35, 0.35, 0.3, 0.3], center: [0.5, 0.5] },
    }] } };
  const outlined = buildScene(input);
  input.scene.marks[0].filled = true;
  const filled = buildScene(input);
  assert.deepEqual(outlined.meshes[0].positions, filled.meshes[0].positions);
  assert.deepEqual(outlined.meshes[0].indices, filled.meshes[0].indices);
  assert.deepEqual(outlined.meshes[0].appearance, input.scene.marks[0].appearance);
  assert.ok(outlined.meshes[0].positions.some((value, index) => index % 3 === 2 && value > 0.11));
});

// Failure: the ideal ellipse clips a loaded brush fringe outside its radius.
test('painted circle radii preserve the outer alpha fringe and ignore transparent RGB', () => {
  const size = 64, data = new Uint8ClampedArray(size * size * 4);
  for (let y = 0; y < size; y++) for (let x = 0; x < size; x++) {
    const offset = (y * size + x) * 4;
    data[offset] = 255;
    if (Math.hypot(x + 0.5 - 32, y + 0.5 - 32) < 20) data[offset + 3] = 255;
  }
  data[(32 * size + 58) * 4 + 3] = 40;
  const radii = paintedRadii(data, size, size, [0, 0, 1, 1], [0.5, 0.5]);
  assert.ok(Math.max(...radii) > 26 / 64);
  assert.ok(Math.max(...radii) < 28 / 64);
  assert.ok(radii.some(radius => radius > 19 / 64 && radius < 21 / 64));
  assert.deepEqual(radii, paintedRadii(data, size, size, [0, 0, 1, 1], [0.5, 0.5]));
});

// Failure: WebKit filters the SVG at its own larger size, or the rewrite reaches a child or the viewBox.
test('raster-sized SVG changes only the root width and height', () => {
  const svg = '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="1300.5" height="900" viewBox="0 0 1300.5 900">'
    + '<rect width="5" height="6"/></svg>';
  assert.equal(rasterSizedSvg(svg, 341, 236), '<?xml version="1.0"?><svg xmlns="http://www.w3.org/2000/svg" width="341" height="236" viewBox="0 0 1300.5 900">'
    + '<rect width="5" height="6"/></svg>');
  const unsized = '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 10 10"><rect width="5" height="6"/></svg>';
  assert.equal(rasterSizedSvg(unsized, 341, 236), unsized);
});
