import test from 'node:test';
import assert from 'node:assert/strict';
import { BOARD, boardShare, buildScene, canvasCoverage, unpackMesh } from './build.ts';
import type { PreparedScene } from './types.ts';

const square = (size: [number, number], filled = true, primitive = 'square'): PreparedScene => ({
  ok: true, inputDigest: '', schemaDigest: '', mappingVersion: '', engineVersion: 1,
  scene: { canvas: [1, 1], background: '#ffffff', ground: false, diagnostics: [], recoveries: [], marks: [{
    sourceIndex: 0, performedIndex: 0, instanceIndex: 0, primitive,
    shape: { kind: 'contour', points: [[0, 0], [size[0], 0], [size[0], size[1]], [0, size[1]]] }, transform: [1, 0, 0, 1, 0, 0],
    color: '#333333', width: 0.004, filled, opacity: 1, dash: [], weight: 'rotring', clips: [],
  }] },
});
const depth = (input: PreparedScene) => {
  const packet = buildScene(input), geometry = unpackMesh(packet.meshes[0]); geometry.computeBoundingBox();
  const box = geometry.boundingBox!; geometry.dispose();
  return { thickness: box.max.z - box.min.z, board: packet.meshes[0].board };
};
const close = (a: number, b: number) => assert.ok(Math.abs(a - b) < 1e-6, `${a} != ${b}`);

test('coverage counts only the part inside the canvas', () => {
  close(canvasCoverage([[0, 0], [1, 0], [1, 1], [0, 1]], [1, 0, 0, 1, 0, 0], [1, 1]), 1);
  close(canvasCoverage([[0, 0], [1, 0], [1, 1], [0, 1]], [1, 0, 0, 1, 0.5, 0], [1, 1]), 0.5);
  close(canvasCoverage([[0, 0], [1, 0], [1, 1], [0, 1]], [2, 0, 0, 2, -0.5, -0.5], [1, 1]), 1);
  close(canvasCoverage([[0, 0], [1, 0], [1, 1], [0, 1]], [1, 0, 0, 1, 2, 0], [1, 1]), 0);
});

// Failure (2026-11-20): a filled square as large as the canvas became a block
// as deep as the canvas, holding every other layer inside it.
test('a filled square over half the canvas is a board; a small one stays a cube', () => {
  assert.equal(boardShare(0.2), 0); assert.equal(boardShare(0.5), 1); close(boardShare(0.35), 0.5);
  const ground = depth(square([1, 0.6]));
  close(ground.thickness, BOARD); assert.equal(ground.board, 1);
  const cube = depth(square([0.24, 0.24]));
  close(cube.thickness, 0.24); assert.equal(cube.board, undefined);
  // Between a fifth and a half, the thickness moves smoothly between the two.
  const between = depth(square([1, 0.35]));
  close(between.thickness, 0.35 + (BOARD - 0.35) * 0.5);
  // Only filled squares: an outline or another shape keeps its own depth.
  assert.equal(depth(square([1, 0.6], false)).board, undefined);
  assert.equal(depth(square([1, 0.6], true, 'polygon')).board, undefined);
});
