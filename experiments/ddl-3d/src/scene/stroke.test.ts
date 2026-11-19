import test from 'node:test';
import assert from 'node:assert/strict';
import { followStroke } from '../viewer/circleAppearance.ts';
import { buildScene, unpackMesh } from './build.ts';
import type { PreparedScene } from './types.ts';

// Failure (2026-11-20, swift's iPhone and the census of 959 works): the core
// gives a line as a straight centre line, the 2D brush wavers off it, and the
// tube stayed transparent wherever the stroke strayed, so lines vanished
// from the front of the solids.
test('a painted line tube moves onto its brush stroke, as wide as the paint', () => {
  const input: PreparedScene = { ok: true, inputDigest: '', schemaDigest: '', mappingVersion: '', engineVersion: 1,
    scene: { canvas: [1, 1], background: '#ffffff', ground: false, diagnostics: [], recoveries: [], marks: [{
      sourceIndex: 0, performedIndex: 0, instanceIndex: 0, primitive: 'line',
      shape: { kind: 'path', points: [[0.1, 0.5], [0.9, 0.5]] }, transform: [1, 0, 0, 1, 0, 0],
      color: '#333333', width: 0.002, filled: false, opacity: 1, dash: [], weight: 'rotring', clips: [],
      appearance: { svg: '<svg/>', bounds: [0, 0.4, 1, 0.2], center: [0.5, 0.5] },
    }] } };
  const packet = buildScene(input), mesh = packet.meshes[0];
  assert.ok(mesh.axis, 'a painted path keeps its ring axes');
  const rings = new Set(Array.from({ length: mesh.axis!.length / 4 }, (_, i) => mesh.axis![i * 4])).size;
  assert.ok(rings >= 40, `${rings} rings along 0.8 of length`);
  // The paint: a band 0.006 wide whose centre runs 0.008 below the line on
  // the paper (canvas y 0.508), i.e. y = -0.008 on the centred plane.
  const width = 1000, height = 200, data = new Uint8ClampedArray(width * height * 4);
  for (let py = 0; py < height; py++) {
    const cy = 0.4 + (py + 0.5) / height * 0.2;
    if (Math.abs(cy - 0.508) <= 0.003) for (let px = 50; px < 950; px++) data[(py * width + px) * 4 + 3] = 255;
  }
  const geometry = unpackMesh(mesh), positions = geometry.getAttribute('position');
  followStroke(positions, mesh.axis!, data, width, height, [0, 0.4, 1, 0.2], [1, 1]);
  const ys = Array.from({ length: positions.count }, (_, i) => positions.getY(i)).filter((_, i) => positions.getX(i) > -0.3 && positions.getX(i) < 0.3);
  const centre = (Math.max(...ys) + Math.min(...ys)) / 2, half = (Math.max(...ys) - Math.min(...ys)) / 2;
  assert.ok(Math.abs(centre - -0.008) < 0.001, `centre ${centre}`);
  assert.ok(Math.abs(half - 0.0035) < 0.001, `half width ${half}`);
  geometry.dispose();
});

test('a line without paint, or a solid, has no ring axes', () => {
  const base = { sourceIndex: 0, performedIndex: 0, instanceIndex: 0, transform: [1, 0, 0, 1, 0, 0] as [number, number, number, number, number, number],
    color: '#333333', width: 0.002, filled: true, opacity: 1, dash: [], weight: 'rotring', clips: [] };
  const packet = buildScene({ ok: true, inputDigest: '', schemaDigest: '', mappingVersion: '', engineVersion: 1,
    scene: { canvas: [1, 1], background: '#ffffff', ground: false, diagnostics: [], recoveries: [], marks: [
      { ...base, primitive: 'line', shape: { kind: 'path', points: [[0.1, 0.5], [0.9, 0.5]] } },
      { ...base, sourceIndex: 1, primitive: 'square', shape: { kind: 'contour', points: [[0.1, 0.1], [0.3, 0.1], [0.3, 0.3], [0.1, 0.3]] } },
    ] } });
  assert.equal(packet.meshes[0].axis, undefined);
  assert.equal(packet.meshes[1].axis, undefined);
});
