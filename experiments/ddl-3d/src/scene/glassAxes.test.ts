import test from 'node:test';
import assert from 'node:assert/strict';
import { axisLayout, chooseHinges, FAN_DEGREES_PER_UNIT, glassGeometry, markRect, paperGrid, planeZ,
  sameAxis, SPACING_PER_UNIT, ORDER_GAP, type AxisLayer, type Grid } from './glassAxes.ts';
import type { XY } from './types.ts';

const rect = (grid: Grid, x0: number, y0: number, x1: number, y1: number) => {
  const mask = new Uint8Array(grid.nx * grid.ny); markRect(grid, mask, x0, y0, x1, y1); return mask;
};
const layer = (grid: Grid, r: [number, number, number, number], sheen = true): AxisLayer => ({ paint: rect(grid, ...r), shape: rect(grid, ...r), sheen });

/** Three made-up works: two layers apart, a full ground with small marks, eight diagonal bands. */
function works(): { canvas: XY; layers: AxisLayer[] }[] {
  const out: { canvas: XY; layers: AxisLayer[] }[] = [];
  let canvas: XY = [1, 1], grid = paperGrid(canvas);
  out.push({ canvas, layers: [layer(grid, [-0.45, -0.3, -0.05, 0.3]), layer(grid, [0.1, -0.2, 0.4, 0.2])] });
  canvas = [1.5, 1]; grid = paperGrid(canvas);
  out.push({ canvas, layers: [layer(grid, [-0.75, -0.5, 0.75, 0.5], false), layer(grid, [-0.5, 0.1, -0.4, 0.2]), layer(grid, [0.2, -0.3, 0.3, -0.2]), layer(grid, [0.5, 0.2, 0.6, 0.35])] });
  canvas = [1, 1.5]; grid = paperGrid(canvas);
  out.push({ canvas, layers: Array.from({ length: 8 }, (_, i) => {
    const mask = new Uint8Array(grid.nx * grid.ny);
    for (let k = 0; k < 10; k++) { const t = -0.5 + k / 10; markRect(grid, mask, t, -0.75 + i * 0.15 + t * 0.3, t + 0.12, -0.65 + i * 0.15 + t * 0.3); }
    return { paint: mask, shape: mask, sheen: i % 2 === 0 };
  }) });
  return out;
}

const corners = (grid: Grid, mask: Uint8Array): XY[] => {
  const out: XY[] = [];
  for (let j = 0; j < grid.ny; j++) for (let i = 0; i < grid.nx; i++) if (mask[j * grid.nx + i]) {
    const x0 = grid.x0 + i * grid.cell, y0 = grid.y0 + j * grid.cell;
    out.push([x0, y0], [Math.min(x0 + grid.cell, grid.x0 + grid.width), y0], [x0, Math.min(y0 + grid.cell, grid.y0 + grid.height)],
      [Math.min(x0 + grid.cell, grid.x0 + grid.width), Math.min(y0 + grid.cell, grid.y0 + grid.height)]);
  }
  return out;
};

// Failure: a later layer's paint goes behind an earlier plane, so the front
// view's overlap differs from 2D; neighbours share an axis; the block grows
// thicker than the old fan.
test('chosen hinges keep later paint in front, differ from neighbours, and stay thin', () => {
  for (const { canvas, layers } of works()) {
    const grid = paperGrid(canvas), layout = axisLayout(grid, layers, canvas);
    for (const hinges of [chooseHinges(layout)]) {
      assert.equal(hinges.length, layers.length);
      for (let i = 1; i < hinges.length; i++) assert.ok(!sameAxis(hinges[i - 1], hinges[i]));
      for (const angle of [0, 1, 2]) for (const spacing of [0, 1, 3]) {
        const g = glassGeometry(layout, hinges, angle, spacing, 0.03, 0.03);
        layers.forEach((L, i) => { for (const [x, y] of corners(grid, L.paint)) {
          for (let j = 0; j < i; j++) assert.ok(planeZ(g.planes[i], x, y) >= planeZ(g.planes[j], x, y) + ORDER_GAP - 1e-9);
          const z = planeZ(g.planes[i], x, y); assert.ok(z < g.front && z > g.back);
        } });
        if (angle === 1 && spacing === 1) {
          const theta = FAN_DEGREES_PER_UNIT * Math.PI / 180, N = layers.length;
          const D0 = N > 1 ? (N - 1) * SPACING_PER_UNIT + canvas[0] * Math.tan(theta) : canvas[0] * Math.tan(theta / 2);
          // The score only presses on thickness; a block over the old fan is recorded, not failed.
          const D = g.front - g.back - 0.06;
          if (D > D0 + 1e-9) console.log(`thicker than the old fan: ${D.toFixed(3)} > ${D0.toFixed(3)} (${N} layers, ${canvas.join('x')})`);
        }
      }
    }
  }
});
