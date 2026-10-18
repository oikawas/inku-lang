import test from 'node:test';
import assert from 'node:assert/strict';
import { Mesh, MeshBasicMaterial } from 'three';
import { buildScene, unpackMesh } from './build.ts';
import { lineDepthAt } from './lineDepth.ts';
import { objectDepth } from '../viewer/objectDepth.ts';
import { mapPaintSurfaces } from '../viewer/circleAppearance.ts';
import type { GeometryMark, PreparedScene, XY } from './types.ts';

const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);
function scene(paths: XY[][]) {
  const marks: GeometryMark[] = paths.map((points, i) => ({
    sourceIndex: i, performedIndex: i, instanceIndex: 0, primitive: 'line', shape: { kind: 'path', points },
    transform: [-1, 0, 0, 1, 1, 0], color: '#336699', width: 0.01, filled: false,
    opacity: 1, dash: [], weight: 'rotring', clips: [],
  }));
  return { ok: true, scene: { canvas: [1, 1], background: '#ffffff', ground: false, marks, diagnostics: [], recoveries: [] },
    inputDigest: 'fixture', schemaDigest: 'fixture', mappingVersion: 'solid-mapping-v1', engineVersion: 85 } as PreparedScene;
}

// Failure: a branch is detached from an interior joint, especially after paint
// expands vertices or thickness scales a depth offset along with the tube.
test('a transformed T joint stays joined at every depth and thickness', () => {
  const input = scene([[[0.1, 0.5], [0.9, 0.5]], [[0.5, 0.5], [0.5, 0.9]]]);
  const original = structuredClone(input), packet = buildScene(input);
  assert.deepEqual(input, original);
  const [host, branch] = packet.meshes;
  assert.equal(host.depthPath!.points.length, 3);
  close(lineDepthAt(host.depthPath!, 0, 0), lineDepthAt(branch.depthPath!, 0, 0));
  assert.notEqual(lineDepthAt(branch.depthPath!, 0, -0.4), lineDepthAt(branch.depthPath!, 0, 0));
  const material = new MeshBasicMaterial();
  const meshes = packet.meshes.map(data => {
    const source = unpackMesh(data), mapped = mapPaintSurfaces(source, [0, 0, 1, 1], [1, 1], true);
    if (mapped !== source) source.dispose();
    return new Mesh(mapped, material);
  });
  const update = meshes.map((mesh, i) => objectDepth(mesh, packet.meshes[i]));
  for (const spacing of [0, 1, 3, 0, 1]) for (const thickness of [0.1, 3]) {
    update.forEach(apply => apply(thickness, spacing));
    const expected = lineDepthAt(host.depthPath!, 0, 0) * spacing;
    const ring = meshes[0].geometry.getAttribute('position');
    const zs = Array.from({ length: ring.count }, (_, i) => i).filter(i => Math.abs(ring.getX(i)) < 1e-7)
      .map(i => ring.getZ(i) + meshes[0].position.z);
    close((Math.min(...zs) + Math.max(...zs)) / 2, expected);
    const end = meshes[1].geometry.getAttribute('position');
    const centers = Array.from({ length: end.count }, (_, i) => i)
      .filter(i => Math.hypot(end.getX(i), end.getY(i)) < 1e-7);
    assert.ok(centers.length > 0);
    const cap = centers.map(i => end.getZ(i) + meshes[1].position.z);
    close((Math.min(...cap) + Math.max(...cap)) / 2, expected);
  }
  meshes.forEach(mesh => mesh.geometry.dispose()); material.dispose();
});

// Failure: a closed chain separates at its last joint, or mere crossings join.
test('closed line chains share all four nodes and interior crossings stay independent', () => {
  const loop = buildScene(scene([[[0.2, 0.2], [0.8, 0.2]], [[0.8, 0.2], [0.8, 0.8]],
    [[0.8, 0.8], [0.2, 0.8]], [[0.2, 0.8], [0.2, 0.2]]]));
  for (let i = 0; i < 4; i++) {
    const first = loop.meshes[i].depthPath!, next = loop.meshes[(i + 1) % 4].depthPath!;
    close(first.depths.at(-1)!, next.depths[0]);
  }
  const crossing = buildScene(scene([[[0.1, 0.5], [0.9, 0.5]], [[0.5, 0.1], [0.5, 0.9]]]));
  assert.ok(crossing.meshes.every(mesh => !mesh.depthPath));
  assert.notEqual(crossing.meshes[0].layerZ, crossing.meshes[1].layerZ);
});

// Failure: moving copies of a rigid solid detaches a connected straight line.
test('a straight endpoint follows the depth of the solid it touches', () => {
  const input = scene([[[0.3, 0.5], [0.9, 0.5]]]);
  input.scene.marks.push({ ...input.scene.marks[0], sourceIndex: 1, performedIndex: 1,
    primitive: 'circle', shape: { kind: 'round', center: [0.2, 0.5], radii: [0.1, 0.1] }, filled: true });
  const [line, solid] = buildScene(input).meshes;
  close(line.depthPath!.depths[0], solid.layerZ);
  close(line.depthPath!.depths.at(-1)!, line.layerZ);
  assert.equal(solid.depthPath, undefined);
});
