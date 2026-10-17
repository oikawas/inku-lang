import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { Box3, Vector3 } from 'three';
import { buildScene, unpackMesh } from './build.ts';
import type { PreparedScene } from './types.ts';
import init, { prepare_scene } from '../../public/wasm/score_adapter.js';

await init({ module_or_path: readFileSync(new URL('../../public/wasm/score_adapter_bg.wasm', import.meta.url)) });
const solidsJson = readFileSync(new URL('../../fixtures/solids.json', import.meta.url), 'utf8');
const recoveredJson = readFileSync(new URL('../../fixtures/recovered-score.json', import.meta.url), 'utf8');
function prepare(json = solidsJson): PreparedScene {
  const result = JSON.parse(prepare_scene(json));
  assert.equal(result.ok, true, result.error);
  return result;
}
function bounds(packet: ReturnType<typeof buildScene>['meshes'][number]) {
  const geometry = unpackMesh(packet); geometry.computeBoundingBox();
  const box = geometry.boundingBox!.clone(); geometry.dispose(); return box;
}
const close = (actual: number, expected: number) => assert.ok(Math.abs(actual - expected) < 1e-6, `${actual} != ${expected}`);

// Failure: every source layer shares Z=0, or scattered copies become separate layers.
test('paint layers keep copies together and place later layers toward positive Z', () => {
  const input = prepare(recoveredJson), original = structuredClone(input);
  const packet = buildScene(input);
  assert.equal(packet.layerCount, 2);
  assert.deepEqual(packet.meshes.map(m => m.layerIndex), [0, 0, 1]);
  assert.deepEqual(packet.meshes.map(m => m.layerZ), [-0.4, -0.4, 0.4]);
  assert.deepEqual(input, original);
  // Paint order, rather than the numeric source ID, determines front/back.
  input.scene.marks.reverse();
  const reversed = buildScene(input);
  assert.deepEqual(reversed.meshes.map(m => m.sourceIndex), [1, 0, 0]);
  assert.deepEqual(reversed.meshes.map(m => m.layerZ), [-0.4, 0.4, 0.4]);
  input.scene.marks = [input.scene.marks[0]];
  assert.equal(buildScene(input).meshes[0].layerZ, 0);
});

// Failure: separating the two arcs tears a shared closed fill apart.
test('paint layers retain closed arc pairs in one plane', () => {
  const score = JSON.parse(readFileSync(new URL('../../../../server/tests/data/score-0.19-maple-leaves-in-cells.json', import.meta.url), 'utf8'));
  const packet = buildScene(prepare(JSON.stringify({ score, render_seed: '9007199254740993' })));
  const pairs = packet.meshes.filter(m => m.role === 'pair-fill');
  assert.equal(pairs.length, 15);
  for (const pair of pairs) {
    for (const mesh of packet.meshes.filter(m => m.sourceIndex === pair.sourceIndex || m.sourceIndex === pair.relatedSourceIndex)) {
      assert.equal(mesh.layerZ, pair.layerZ);
      assert.equal(mesh.layerIndex, pair.layerIndex);
    }
  }
});

// Failure: the WASM recovery survives conversion but is dropped by the Worker packet.
test('recovered Score renders all retained geometry and carries diagnostics to the viewer', () => {
  const input = prepare(recoveredJson), packet = buildScene(input);
  assert.equal(packet.objectCount, 3);
  assert.deepEqual(packet.meshes.map(m => m.sourceIndex), [0, 0, 1]);
  assert.ok(packet.triangles > 0);
  assert.deepEqual(packet.recoveries, input.scene.recoveries);
  assert.equal(packet.recoveries[0].disposition, 'relation_omitted');
});

// Failure: round/rectangle become flat planes or stretch with the canvas aspect.
test('WASM to solids preserves aspect, source identities, volume and deterministic buffers', () => {
  const input = prepare(), first = buildScene(input), second = buildScene(prepare());
  assert.equal(first.objectCount, 9); assert.equal(first.meshes.length, 9);
  assert.deepEqual(first, second);
  const sphere = bounds(first.meshes[0]), cube = bounds(first.meshes[1]);
  const size = sphere.getSize(new Vector3());
  close(size.x, 0.24); close(size.y, 0.24); close(size.z, 0.24);
  close(sphere.getCenter(new Vector3()).x, -0.42); close(sphere.getCenter(new Vector3()).y, 0.25);
  const cubeSize = cube.getSize(new Vector3());
  close(cubeSize.x, 0.2); close(cubeSize.y, 0.2); close(cubeSize.z, 0.2);
  assert.ok(first.meshes.every(m => bounds(m).getSize(new Vector3()).z > 0));
  assert.deepEqual(first.meshes.map(m => m.sourceIndex), [0, 1, 2, 3, 4, 5, 6, 7, 8]);
});

// Failure: clipping is only visual and exported vertices still extend outside it.
test('fill clipping modifies the actual solid vertices', () => {
  const input = prepare(); input.scene.marks = [input.scene.marks[0]];
  input.scene.marks[0].clips = [[[0.28, 0], [1.4, 0], [1.4, 1], [0.28, 1]]];
  const packet = buildScene(input), box = bounds(packet.meshes[0]);
  close(box.min.x, -0.42); close(box.max.x, -0.30);
  assert.ok(packet.triangles > 0);
});

// Failure: affine reflection reverses faces or uniform group scale leaves Z behind.
test('group transforms preserve solid volume and facing', () => {
  const input = prepare(); input.scene.marks = [input.scene.marks[1]];
  input.scene.marks[0].transform = [-2, 0, 0, 2, 1.4, 0];
  const mesh = buildScene(input).meshes[0], size = bounds(mesh).getSize(new Vector3());
  close(size.x, 0.4); close(size.y, 0.4); close(size.z, 0.4);
  const vertices = mesh.positions, index = mesh.indices ?? Array.from({ length: vertices.length / 3 }, (_, i) => i);
  let volume = 0;
  for (let i = 0; i < index.length; i += 3) {
    const a = new Vector3().fromArray(vertices, index[i] * 3), b = new Vector3().fromArray(vertices, index[i + 1] * 3), c = new Vector3().fromArray(vertices, index[i + 2] * 3);
    volume += a.dot(b.cross(c)) / 6;
  }
  close(volume, 0.064);
});

// Failure: malformed data reaches GPU buffers or a larger scene silently loses objects.
test('invalid geometry and excessive mesh demand are explicit failures', () => {
  const input = prepare(); input.scene.marks[0].transform[0] = NaN;
  assert.throws(() => buildScene(input), /invalid_transform/);
  const big = prepare(); big.scene.marks = Array.from({ length: 4096 }, () => big.scene.marks[0]);
  assert.throws(() => buildScene(big), /mesh_budget_exceeded/);
});

// Failure: a few dozen painted rounds exceed the budget despite a small Score.
test('many painted rounds retain every source and appearance within the mesh limit', () => {
  const input = prepare();
  const mark = input.scene.marks.find(m => m.appearance)!;
  input.scene.marks = Array.from({ length: 120 }, (_, i) => ({ ...mark, sourceIndex: i, performedIndex: i }));
  input.scene.presenceSvg = '<svg xmlns="http://www.w3.org/2000/svg" width="1" height="1"/>';
  const original = structuredClone(input), packet = buildScene(input);
  assert.equal(packet.objectCount, 120); assert.equal(packet.meshes.length, 120);
  assert.ok(packet.triangles > 0 && packet.triangles <= 500_000);
  assert.deepEqual(packet.meshes.map(m => m.sourceIndex), Array.from({ length: 120 }, (_, i) => i));
  assert.ok(packet.meshes.every(m => m.appearance === mark.appearance));
  assert.equal(packet.presenceSvg, input.scene.presenceSvg);
  assert.deepEqual(input, original);
});

// Failure: the core's free line is flattened into its two endpoints.
test('free line keeps a curved centerline and a solid tube', () => {
  const value = JSON.parse(solidsJson);
  value.score.version = '0.21.0';
  value.score.instructions = [{ primitive: 'free_line', from: [0.1, 0.5], to: [0.9, 0.5], color: 'blue', weight: 'rotring' }];
  const input = prepare(JSON.stringify(value));
  const shape = input.scene.marks[0].shape;
  assert.equal(shape.kind, 'path');
  if (shape.kind === 'path') { assert.ok(shape.points.length > 2); assert.ok(shape.points.some(p => Math.abs(p[1] - 0.5) > 0.001)); }
  const box = bounds(buildScene(input).meshes[0]);
  assert.ok(box.getSize(new Vector3()).z > 0);
});

// Failure: placement/arc closure is lost between WASM and the mesh adapter.
test('saved maple fixture creates all three placed leaves with closed interiors', () => {
  const score = JSON.parse(readFileSync(new URL('../../../../server/tests/data/score-0.19-maple-leaves-in-cells.json', import.meta.url), 'utf8'));
  const input = prepare(JSON.stringify({ score, render_seed: '9007199254740993' }));
  const packet = buildScene(input);
  assert.equal(packet.objectCount, 33); assert.equal(packet.meshes.filter(m => m.role === 'pair-fill').length, 15);
  assert.ok(packet.meshes.every(m => !bounds(m).isEmpty()));
});
