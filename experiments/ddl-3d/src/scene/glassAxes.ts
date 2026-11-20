import type { MeshPacket, XY } from './types.ts';

/**
 * Hinges for the glass layers, chosen per work.
 *
 * Each layer is a leaf that rises about one hinge line on the paper:
 * z = r + tan(theta) * (u . p - m). The hinge lines come from a small set
 * fixed by the paper (vertical, horizontal and the two diagonal directions,
 * at the edges, quarters and centre), and the angles are fixed parts of the
 * plane angle; the work's marks choose which line each layer uses.
 *
 * Coordinates are the viewer's world: the paper's centre at the origin, y up.
 */

/** The grid has this many cells along the paper's long side. */
export const GRID_LONG = 48;
/** A later layer's paint stays at least this far in front of every earlier plane. */
export const ORDER_GAP = 0.002;
/** "Plane angle" 1 is this many degrees; "Layer depth" 1 parts layers by this much. */
export const FAN_DEGREES_PER_UNIT = 24;
export const SPACING_PER_UNIT = 0.02;
/** Parts of the plane angle a hinge may open by. */
export const FRACTIONS = [0.25, 0.5, 1] as const;
const POSITIONS = 5;
const DIRECTIONS = 8;
const DEG = Math.PI / 180;

/** A layer's hinge: flat, or a direction (0 right, then counter-clockwise in
 * 45 degree steps), a line (0 at the edge opposite the rise, 4 at the far
 * edge) and a part of the plane angle. */
export type Hinge = { flat: true } | { flat?: false; dir: number; pos: number; frac: number };

export interface Grid { nx: number; ny: number; cell: number; x0: number; y0: number; width: number; height: number }

export function paperGrid(canvas: XY): Grid {
  const [width, height] = canvas, cell = Math.max(width, height) / GRID_LONG;
  return { nx: Math.max(1, Math.ceil(width / cell - 1e-9)), ny: Math.max(1, Math.ceil(height / cell - 1e-9)), cell, x0: -width / 2, y0: -height / 2, width, height };
}

/** Cell bounds clipped to the paper. */
function cellBox(grid: Grid, i: number, j: number): [number, number, number, number] {
  const x0 = grid.x0 + i * grid.cell, y0 = grid.y0 + j * grid.cell;
  return [x0, y0, Math.min(x0 + grid.cell, grid.x0 + grid.width), Math.min(y0 + grid.cell, grid.y0 + grid.height)];
}

/** Cells a rectangle (world) meets; an edge lying on a cell border does not count. */
export function markRect(grid: Grid, mask: Uint8Array, xa: number, ya: number, xb: number, yb: number) {
  const i0 = Math.max(0, Math.floor((xa - grid.x0) / grid.cell)), i1 = Math.min(grid.nx, Math.ceil((xb - grid.x0) / grid.cell));
  const j0 = Math.max(0, Math.floor((ya - grid.y0) / grid.cell)), j1 = Math.min(grid.ny, Math.ceil((yb - grid.y0) / grid.cell));
  for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) mask[j * grid.nx + i] = 1;
}

/** Cells a triangle overlaps with some area (separating axes). */
export function markTriangle(grid: Grid, mask: Uint8Array, ax: number, ay: number, bx: number, by: number, cx: number, cy: number) {
  const area = (bx - ax) * (cy - ay) - (cx - ax) * (by - ay);
  if (!(Math.abs(area) > 1e-14)) return;
  const xs = [ax, bx, cx], ys = [ay, by, cy];
  const i0 = Math.max(0, Math.floor((Math.min(...xs) - grid.x0) / grid.cell)), i1 = Math.min(grid.nx, Math.ceil((Math.max(...xs) - grid.x0) / grid.cell));
  const j0 = Math.max(0, Math.floor((Math.min(...ys) - grid.y0) / grid.cell)), j1 = Math.min(grid.ny, Math.ceil((Math.max(...ys) - grid.y0) / grid.cell));
  const edges: XY[] = [[ay - by, bx - ax], [by - cy, cx - bx], [cy - ay, ax - cx]];
  for (let j = j0; j < j1; j++) for (let i = i0; i < i1; i++) {
    if (mask[j * grid.nx + i]) continue;
    const [x0, y0, x1, y1] = cellBox(grid, i, j);
    if (Math.max(...xs) <= x0 || Math.min(...xs) >= x1 || Math.max(...ys) <= y0 || Math.min(...ys) >= y1) continue;
    let apart = false;
    for (const [nx, ny] of edges) {
      const t = [ax * nx + ay * ny, bx * nx + by * ny, cx * nx + cy * ny];
      const b = [x0 * nx + y0 * ny, x1 * nx + y0 * ny, x0 * nx + y1 * ny, x1 * nx + y1 * ny];
      if (Math.max(...t) <= Math.min(...b) || Math.max(...b) <= Math.min(...t)) { apart = true; break; }
    }
    if (!apart) mask[j * grid.nx + i] = 1;
  }
}

/** OKLab lightness and chroma of a #rrggbb colour. */
export function oklab(color: string): { lightness: number; chroma: number } {
  const value = parseInt(color.slice(1), 16);
  const lin = (x: number) => x <= 0.04045 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4;
  const [r, g, b] = [(value >> 16) & 255, (value >> 8) & 255, value & 255].map(v => lin(v / 255));
  const l = Math.cbrt(0.4122214708 * r + 0.5363325363 * g + 0.0514459929 * b);
  const m = Math.cbrt(0.2119034982 * r + 0.6806995451 * g + 0.1073969566 * b);
  const s = Math.cbrt(0.0883024619 * r + 0.2817188376 * g + 0.6299787005 * b);
  return { lightness: 0.2104542553 * l + 0.7936177850 * m - 0.0040720468 * s,
    chroma: Math.hypot(1.9779984951 * l - 2.4285922050 * m + 0.4505937099 * s, 0.0259040371 * l + 0.7827717662 * m - 0.8086757660 * s) };
}
/** White marks do not brighten under the leaf; a layer of them shows no sheen. */
export function showsSheen(color: string): boolean {
  const { lightness, chroma } = oklab(color);
  return lightness < 0.92 || chroma >= 0.035;
}

/** A layer as the hinge choice sees it: where its paint can be, where its marks are, and whether it shines. */
export interface AxisLayer { paint: Uint8Array; shape: Uint8Array; sheen: boolean }

/** Paint cells from the marks' appearance bounds (the core keeps the brush
 * fringe inside them), shape cells from the marks' nominal footprints. */
export function axisLayers(groups: readonly (readonly MeshPacket[])[], canvas: XY): { grid: Grid; layers: AxisLayer[] } {
  const grid = paperGrid(canvas), [W, H] = canvas;
  const layers = groups.map(marks => {
    const paint = new Uint8Array(grid.nx * grid.ny), shape = new Uint8Array(grid.nx * grid.ny);
    for (const mark of marks) {
      const bounds = mark.appearance?.bounds;
      if (bounds) markRect(grid, paint, bounds[0] - W / 2, H / 2 - bounds[1] - bounds[3], bounds[0] + bounds[2] - W / 2, H / 2 - bounds[1]);
      if (mark.outline) {
        // An unfilled ring: a thin band along its outline.
        const o = mark.outline, half = grid.cell / 4, n = o.length / 2;
        for (let k = 0; k < n; k++) {
          const ax = o[2 * k], ay = o[2 * k + 1], bx = o[(2 * k + 2) % o.length], by = o[(2 * k + 3) % o.length];
          const len = Math.hypot(bx - ax, by - ay) || 1, px = -(by - ay) / len * half, py = (bx - ax) / len * half;
          markTriangle(grid, shape, ax + px, ay + py, bx + px, by + py, bx - px, by - py);
          markTriangle(grid, shape, ax + px, ay + py, bx - px, by - py, ax - px, ay - py);
        }
      } else {
        const p = mark.positions, idx = mark.indices, count = idx ? idx.length : p.length / 3;
        for (let t = 0; t + 2 < count; t += 3) {
          const a = idx ? idx[t] : t, b = idx ? idx[t + 1] : t + 1, c = idx ? idx[t + 2] : t + 2;
          const ax = p[3 * a], ay = p[3 * a + 1], bx = p[3 * b], by = p[3 * b + 1], cx = p[3 * c], cy = p[3 * c + 1];
          // The front half of a closed solid covers its whole footprint.
          if ((bx - ax) * (cy - ay) - (cx - ax) * (by - ay) <= 0) continue;
          markTriangle(grid, shape, ax, ay, bx, by, cx, cy);
        }
      }
    }
    if (!paint.some(Boolean)) paint.fill(1);
    if (!shape.some(Boolean)) shape.set(paint);
    return { paint, shape, sheen: marks.some(mark => showsSheen(mark.color)) };
  });
  return { grid, layers };
}

// Lights ---------------------------------------------------------------------

export interface RectLight { c: [number, number, number]; n: [number, number, number]; u: [number, number, number]; v: [number, number, number]; hu: number; hv: number; power: number }
type V3 = [number, number, number];
const dot = (a: V3, b: V3) => a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
const norm = (a: V3): V3 => { const l = Math.hypot(...a) || 1; return [a[0] / l, a[1] / l, a[2] / l]; };
const cross = (a: V3, b: V3): V3 => [a[1] * b[2] - a[2] * b[1], a[2] * b[0] - a[0] * b[2], a[0] * b[1] - a[1] * b[0]];
const turn = (p: V3, az: number, el: number): V3 => {
  // Turn about the vertical axis, then raise toward +y.
  const x = p[0] * Math.cos(az) - p[2] * Math.sin(az), z = p[0] * Math.sin(az) + p[2] * Math.cos(az);
  const y = p[1] * Math.cos(el) + z * Math.sin(el), z2 = z * Math.cos(el) - p[1] * Math.sin(el);
  return [x, y, z2];
};

/** Lights A (tall, on the left; follows the pointer and the light control),
 * B (wide, above) and D (square, lower right; follows with A). Sizes follow
 * the paper's long side. `pointer` is -1..1 in x and y. */
export function glassLights(canvas: XY, light = 0, pointer: XY = [0, 0]): RectLight[] {
  const L = Math.max(...canvas), shift = (15 * light + 15 * pointer[0]) * DEG, rise = 8 * pointer[1] * DEG;
  const az = 50 * DEG + shift;
  const a: V3 = [-Math.sin(az) * Math.cos(rise) * 1.6 * L, Math.sin(rise) * 1.6 * L, Math.cos(az) * Math.cos(rise) * 1.6 * L];
  const d = turn([0.95 * L, -0.75 * L, 1.30 * L], -shift, rise);
  return ([[a, 0.15 * L, 1.0 * L, 1.0], [[-0.52 * L, 0.95 * L, 1.43 * L], 1.1 * L, 0.25 * L, 0.7], [d, 0.5 * L, 0.5 * L, 0.5]] as [V3, number, number, number][])
    .map(([c, hu, hv, power]) => { const n = norm(c), u = norm(cross([0, 1, 0], n)), v = norm(cross(n, u)); return { c, n, u, v, hu, hv, power }; });
}

function meets(lights: readonly RectLight[], q: V3, d: V3): boolean {
  for (const L of lights) {
    const den = dot(d, L.n); if (den <= 1e-4) continue;
    const t = (dot(L.c, L.n) - dot(q, L.n)) / den; if (t <= 0) continue;
    const h: V3 = [q[0] + d[0] * t - L.c[0], q[1] + d[1] * t - L.c[1], q[2] + d[2] * t - L.c[2]];
    if (Math.abs(dot(h, L.u)) < L.hu && Math.abs(dot(h, L.v)) < L.hv) return true;
  }
  return false;
}
function refract(d: V3, n: V3, eta: number): V3 | null {
  let c = -dot(n, d); let m = n;
  if (c < 0) { m = [-n[0], -n[1], -n[2]]; c = -c; }
  const k = 1 - eta * eta * (1 - c * c); if (k < 0) return null;
  const f = eta * c - Math.sqrt(k);
  return norm([d[0] * eta + m[0] * f, d[1] * eta + m[1] * f, d[2] * eta + m[2] * f]);
}
/** Whether, seen from direction `view` (toward the viewer), a leaf at q with
 * gradient (gx, gy) shows a light through the front face. */
export function glints(lights: readonly RectLight[], q: V3, gx: number, gy: number, view: V3): boolean {
  const inside = refract([-view[0], -view[1], -view[2]], [0, 0, 1], 1 / 1.5); if (!inside) return false;
  const n = norm([-gx, -gy, 1]), k = 2 * dot(inside, n);
  const r: V3 = [inside[0] - n[0] * k, inside[1] - n[1] * k, inside[2] - n[2] * k];
  if (r[2] <= 0) return false;
  const out = refract(r, [0, 0, -1], 1.5); if (!out) return false;
  return meets(lights, q, out);
}
export function viewDirection(azDeg: number, elDeg: number): V3 {
  const az = azDeg * DEG, el = elDeg * DEG;
  return [Math.sin(az) * Math.cos(el), Math.sin(el), Math.cos(az) * Math.cos(el)];
}

/** The views the rhythm term counts: 10 to 40 degrees from the front, 4 degree steps. */
const VIEWS = (() => {
  const views: { dir: V3; weight: number; az: number; el: number }[] = [];
  for (let el = -40; el <= 40; el += 4) for (let az = -40; az <= 40; az += 4) {
    const dir = viewDirection(az, el), angle = Math.acos(Math.min(1, dir[2])) / DEG;
    if (angle >= 10 - 1e-9 && angle <= 40 + 1e-9) views.push({ dir, weight: Math.cos(angle * DEG) ** 2, az, el });
  }
  return views;
})();
const VIEW_WEIGHT = VIEWS.reduce((s, v) => s + v.weight, 0);

// Precomputed facts of each layer ---------------------------------------------

interface LayerFacts {
  hull: XY[]; centroid: XY; coverage: number; extent: number;
  /** Per direction: min and max of u.p over shape centres and over shape cell corners. */
  centres: [number, number][]; corners: [number, number][];
  /** Per gradient (flat, then dir x frac): the views that glint. */
  glint: Uint8Array[]; glintShare: number[]; sheen: boolean;
}

function directionsFor(canvas: XY): XY[] {
  const [W, H] = canvas, d = Math.hypot(W, H);
  return [[1, 0], [H / d, W / d], [0, 1], [-H / d, W / d], [-1, 0], [-H / d, -W / d], [0, -1], [H / d, -W / d]];
}
/** The hinge line's u.p for a direction and position. */
function hingeAt(canvas: XY, u: XY, pos: number): number {
  const half = (Math.abs(u[0]) * canvas[0] + Math.abs(u[1]) * canvas[1]) / 2;
  return -half + pos / (POSITIONS - 1) * 2 * half;
}

function convexHull(points: XY[]): XY[] {
  const p = [...points].sort((a, b) => a[0] - b[0] || a[1] - b[1]);
  if (p.length < 3) return p;
  const side = (o: XY, a: XY, b: XY) => (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0]);
  const lower: XY[] = [], upper: XY[] = [];
  for (const q of p) { while (lower.length >= 2 && side(lower[lower.length - 2], lower[lower.length - 1], q) <= 0) lower.pop(); lower.push(q); }
  for (const q of p.reverse()) { while (upper.length >= 2 && side(upper[upper.length - 2], upper[upper.length - 1], q) <= 0) upper.pop(); upper.push(q); }
  return lower.slice(0, -1).concat(upper.slice(0, -1));
}

/** How far a layer is ground: 0 below a fifth of the paper, 1 from half of it
 * (the same curve as the solids' board, the author's choice of 2026-11-20). */
export function groundShare(coverage: number): number {
  const t = Math.min(1, Math.max(0, (coverage - 0.2) / 0.3));
  return t * t * (3 - 2 * t);
}

function gradientIndex(h: Hinge): number { return h.flat ? 0 : 1 + h.dir * FRACTIONS.length + h.frac; }

function layerFacts(grid: Grid, layer: AxisLayer, canvas: XY, dirs: XY[], theta: number, lights: RectLight[]): LayerFacts {
  const corners: XY[] = [], centres: XY[] = [], shapeCorners: XY[] = [];
  let area = 0;
  for (let j = 0; j < grid.ny; j++) for (let i = 0; i < grid.nx; i++) {
    const [x0, y0, x1, y1] = cellBox(grid, i, j), k = j * grid.nx + i;
    if (layer.paint[k]) corners.push([x0, y0], [x1, y0], [x0, y1], [x1, y1]);
    if (layer.shape[k]) { centres.push([(x0 + x1) / 2, (y0 + y1) / 2]); shapeCorners.push([x0, y0], [x1, y0], [x0, y1], [x1, y1]); area += (x1 - x0) * (y1 - y0); }
  }
  const centroid: XY = [centres.reduce((s, p) => s + p[0], 0) / centres.length, centres.reduce((s, p) => s + p[1], 0) / centres.length];
  const range = (points: XY[], u: XY): [number, number] => {
    let lo = Infinity, hi = -Infinity;
    for (const p of points) { const m = u[0] * p[0] + u[1] * p[1]; if (m < lo) lo = m; if (m > hi) hi = m; }
    return [lo, hi];
  };
  const xr = range(centres, [1, 0]), yr = range(centres, [0, 1]);
  // Five points the rhythm looks at: the centroid and the farthest shape cell in each quadrant of the paper.
  const samples: XY[] = [centroid];
  for (const [sx, sy] of [[1, 1], [-1, 1], [-1, -1], [1, -1]]) {
    let best: XY | null = null, far = -1;
    for (const p of centres) {
      if (Math.sign(p[0]) !== sx || Math.sign(p[1]) !== sy) continue;
      const d = Math.hypot(p[0] - centroid[0], p[1] - centroid[1]);
      if (d > far) { far = d; best = p; }
    }
    if (best) samples.push(best);
  }
  const glint: Uint8Array[] = [], glintShare: number[] = [];
  const gradients: XY[] = [[0, 0]];
  for (const u of dirs) for (const f of FRACTIONS) { const t = Math.tan(f * theta); gradients.push([t * u[0], t * u[1]]); }
  for (const [gx, gy] of gradients) {
    const seen = new Uint8Array(VIEWS.length); let share = 0;
    VIEWS.forEach((view, v) => {
      if (samples.some(([x, y]) => glints(lights, [x, y, 0], gx, gy, view.dir))) { seen[v] = 1; share += view.weight; }
    });
    glint.push(seen); glintShare.push(share / VIEW_WEIGHT);
  }
  return { hull: convexHull(corners), centroid, coverage: area / (canvas[0] * canvas[1]),
    extent: Math.max(xr[1] - xr[0], yr[1] - yr[0]) + grid.cell,
    centres: dirs.map(u => range(centres, u)), corners: dirs.map(u => range(shapeCorners, u)), glint, glintShare, sheen: layer.sheen };
}

// Geometry ---------------------------------------------------------------------

/** z = c + gx * x + gy * y */
export interface GlassPlane { gx: number; gy: number; c: number }
export interface GlassGeometry {
  planes: GlassPlane[];
  /** Front and back faces of the block (z), after centring. */
  front: number; back: number;
  /** Subtracted from every z so the block's centre is at z = 0. */
  shift: number;
}
export const planeZ = (plane: GlassPlane, x: number, y: number) => plane.c + plane.gx * x + plane.gy * y;

interface Solved { planes: GlassPlane[]; zmin: number; zmax: number }

/** Planes for hinges: each rest depth is the shallowest that keeps the layer's
 * paint in front of every earlier plane (solved with no spacing), then layer
 * i moves forward by i * spacing so the spacing parts all layers alike. */
function solve(hinges: readonly Hinge[], hulls: readonly XY[][], canvas: XY, theta: number, spacing: number, dirs: XY[]): Solved {
  const base: GlassPlane[] = [];
  let zmin = Infinity, zmax = -Infinity;
  hinges.forEach((h, i) => {
    let gx = 0, gy = 0, offset = 0;
    if (!h.flat) {
      const u = dirs[h.dir], t = Math.tan(FRACTIONS[h.frac] * theta);
      gx = t * u[0]; gy = t * u[1]; offset = -t * hingeAt(canvas, u, h.pos);
    }
    let r = 0;
    if (i > 0) {
      r = -Infinity;
      for (let j = 0; j < i; j++) for (const [x, y] of hulls[i]) r = Math.max(r, planeZ(base[j], x, y) + ORDER_GAP - (offset + gx * x + gy * y));
    }
    base.push({ gx, gy, c: r + offset });
  });
  const planes = base.map((p, i) => ({ ...p, c: p.c + i * spacing }));
  planes.forEach((p, i) => { for (const [x, y] of hulls[i]) { const z = planeZ(p, x, y); zmin = Math.min(zmin, z); zmax = Math.max(zmax, z); } });
  return { planes, zmin, zmax };
}

export interface AxisLayout {
  canvas: XY; dirs: XY[]; facts: LayerFacts[];
}

/** Facts for choosing: computed once, at plane angle 1, layer depth 1 and the light control 0. */
export function axisLayout(grid: Grid, layers: readonly AxisLayer[], canvas: XY): AxisLayout {
  const dirs = directionsFor(canvas), lights = glassLights(canvas);
  return { canvas, dirs, facts: layers.map(layer => layerFacts(grid, layer, canvas, dirs, FAN_DEGREES_PER_UNIT * DEG, lights)) };
}

/** The block for chosen hinges at the current controls. */
export function glassGeometry(layout: AxisLayout, hinges: readonly Hinge[], angle: number, spacing: number, frontGlass: number, backGlass: number): GlassGeometry {
  const solved = solve(hinges, layout.facts.map(f => f.hull), layout.canvas, angle * FAN_DEGREES_PER_UNIT * DEG, spacing * SPACING_PER_UNIT, layout.dirs);
  const front = solved.zmax + frontGlass, back = solved.zmin - backGlass, shift = (front + back) / 2;
  return { planes: solved.planes.map(p => ({ ...p, c: p.c - shift })), front: front - shift, back: back - shift, shift };
}

// Score --------------------------------------------------------------------------

const lineKey = (h: Hinge) => h.flat ? -1 : (h.dir < 4 ? h.dir * POSITIONS + h.pos : (h.dir - 4) * POSITIONS + (POSITIONS - 1 - h.pos));
export const sameAxis = (a: Hinge, b: Hinge) => !a.flat && !b.flat && lineKey(a) === lineKey(b);

export interface ScoreParts { order: number; lift: number; ground: number; tilt: number; rhythm: number; depth: number; total: number }
export const WEIGHTS = { order: 2, lift: 1, ground: 1, tilt: 0.5, rhythm: 1, depth: 2 };

/** A partial arrangement: the first layers placed, with running sums, so a
 * search adds one layer at a time without recomputing the others. */
interface Placed {
  hinges: Hinge[]; key: number[];
  /** Planes solved with no spacing (the final plane i adds i * spacing). */
  base: GlassPlane[];
  prevMean: number; zmin: number; zmax: number;
  counts: Uint8Array; none: number; crowd: number; low: number; shining: number;
  order: number; lift: number; ground: number; tilt: number;
  score: number;
}

interface ScoreContext {
  layout: AxisLayout; theta: number; s: number; S: number; T: number; N: number; D0: number;
  /** Per layer and gradient: the views that glint, as indices. */
  glintLists: Int16Array[][];
}

function scoreContext(layout: AxisLayout): ScoreContext {
  const theta = FAN_DEGREES_PER_UNIT * DEG, s = SPACING_PER_UNIT, { canvas } = layout, N = layout.facts.length;
  const S = Math.min(...canvas);
  return { layout, theta, s, S, T: S * 0.5 * Math.tan(theta / 2), N,
    D0: N > 1 ? (N - 1) * s + canvas[0] * Math.tan(theta) : canvas[0] * Math.tan(theta / 2),
    glintLists: layout.facts.map(f => f.glint.map(seen => Int16Array.from([...seen].flatMap((v, k) => v ? [k] : [])))) };
}

const EMPTY: Omit<Placed, 'counts'> = { hinges: [], key: [], base: [], prevMean: 0, zmin: Infinity, zmax: -Infinity,
  none: VIEW_WEIGHT, crowd: 0, low: 0, shining: 0, order: 0, lift: 0, ground: 0, tilt: 0, score: 0 };
const startPlaced = (): Placed => ({ ...EMPTY, key: [], counts: new Uint8Array(VIEWS.length) });

/** The score with one more layer; `keep` also returns the new partial arrangement. */
function extend(ctx: ScoreContext, placed: Placed, h: Hinge, keep: boolean): { score: number; next?: Placed; parts?: ScoreParts } {
  const { layout, theta, s, S, T, N, D0 } = ctx, i = placed.hinges.length, f = layout.facts[i];
  let gx = 0, gy = 0, offset = 0, L = 0, ground = 0, tilt = 0;
  const gamma = groundShare(f.coverage);
  if (!h.flat) {
    const u = layout.dirs[h.dir], t = Math.tan(FRACTIONS[h.frac] * theta), m = hingeAt(layout.canvas, u, h.pos);
    gx = t * u[0]; gy = t * u[1]; offset = -t * m;
    L = t * (u[0] * f.centroid[0] + u[1] * f.centroid[1] - m);
    const [lo, hi] = f.corners[h.dir];
    ground = gamma * t * Math.max(Math.abs(lo - m), Math.abs(hi - m)) / T;
    const [clo, chi] = f.centres[h.dir], need = f.extent * Math.tan(theta / 2) * 0.5;
    tilt = (1 - gamma) * Math.max(0, need - t * (chi - clo)) / need;
  }
  // The shallowest rest depth that keeps this layer's paint in front of every earlier plane.
  let r = 0;
  if (i > 0) {
    r = -Infinity;
    for (const p of placed.base) for (const [x, y] of f.hull) r = Math.max(r, p.c + p.gx * x + p.gy * y + ORDER_GAP - (offset + gx * x + gy * y));
  }
  const base = { gx, gy, c: r + offset }, c = base.c + i * s;
  const mean = c + gx * f.centroid[0] + gy * f.centroid[1];
  const order = placed.order + (i > 0 ? Math.max(0, placed.prevMean + s - mean) / T : 0);
  const target = N > 1 ? Math.max(S * 0.5 * Math.tan(i * theta / (N - 1)), T / 2) : T;
  const lift = placed.lift + (1 - gamma) * ((L - target) / T) ** 2 / N;
  let zmin = placed.zmin, zmax = placed.zmax;
  for (const [x, y] of f.hull) { const z = c + gx * x + gy * y; if (z < zmin) zmin = z; if (z > zmax) zmax = z; }
  // Rhythm: some shining layer catches a light wherever one turns; few views light three at once.
  let none = placed.none, crowd = placed.crowd, low = placed.low, shining = placed.shining;
  const g = gradientIndex(h), list = ctx.glintLists[i][g];
  if (f.sheen) {
    shining++;
    if (f.glintShare[g] < 0.03) low++;
    for (const v of list) { const n = placed.counts[v]; if (n === 0) none -= VIEWS[v].weight; else if (n === 2) crowd += VIEWS[v].weight; }
  }
  const rhythm = shining ? (none + crowd) / VIEW_WEIGHT + low / N : 0;
  const depth = Math.max(0, zmax - zmin - D0) / D0;
  const parts = { order, lift, ground: placed.ground + ground, tilt: placed.tilt + tilt, rhythm, depth };
  const sum = (Object.keys(WEIGHTS) as (keyof typeof WEIGHTS)[]).reduce((acc, k) => acc + WEIGHTS[k] * parts[k], 0);
  const score = Math.round(sum * 1e9) / 1e9;
  if (!keep) return { score };
  const counts = placed.counts.slice();
  if (f.sheen) for (const v of list) counts[v]++;
  return { score, parts: { ...parts, total: score }, next: { hinges: [...placed.hinges, h], key: [...placed.key, hingeNumber(h)], base: [...placed.base, base],
    prevMean: mean, zmin, zmax, counts, none, crowd, low, shining, order, lift, ground: parts.ground, tilt: parts.tilt, score } };
}

/** The beauty score of the first hinges.length layers (smaller is better). */
export function scoreHinges(layout: AxisLayout, hinges: readonly Hinge[]): ScoreParts {
  const ctx = scoreContext(layout);
  let placed = startPlaced(), parts: ScoreParts = { order: 0, lift: 0, ground: 0, tilt: 0, rhythm: 0, depth: 0, total: 0 };
  for (const h of hinges) { const step = extend(ctx, placed, h, true); placed = step.next!; parts = step.parts!; }
  return parts;
}

// Search -------------------------------------------------------------------------

/** Every hinge in number order: flat, then direction, line, part. */
export function allHinges(): Hinge[] {
  const list: Hinge[] = [{ flat: true }];
  for (let dir = 0; dir < DIRECTIONS; dir++) for (let pos = 0; pos < POSITIONS; pos++) for (let frac = 0; frac < FRACTIONS.length; frac++) list.push({ dir, pos, frac });
  return list;
}
const hingeNumber = (h: Hinge) => h.flat ? 0 : 1 + (h.dir * POSITIONS + h.pos) * FRACTIONS.length + h.frac;

type Beam = Placed;
const better = (a: { score: number; key: number[] }, b: { score: number; key: number[] }) => a.score - b.score || compareKeys(a.key, b.key);
function compareKeys(a: number[], b: number[]) { for (let i = 0; i < Math.min(a.length, b.length); i++) if (a[i] !== b[i]) return a[i] - b[i]; return a.length - b.length; }

function beamSearch(ctx: ScoreContext, options: (i: number) => Hinge[], width: number): Beam | null {
  let beams: Beam[] = [startPlaced()];
  for (let i = 0; i < ctx.N; i++) {
    // Score every extension, then build only the ones that survive.
    const next: { beam: Beam; h: Hinge; score: number; key: number[] }[] = [];
    for (const beam of beams) for (const h of options(i)) {
      if (i > 0 && sameAxis(beam.hinges[i - 1], h)) continue;
      next.push({ beam, h, score: extend(ctx, beam, h, false).score, key: [...beam.key, hingeNumber(h)] });
    }
    if (!next.length) return null;
    next.sort(better);
    beams = next.slice(0, width).map(({ beam, h }) => extend(ctx, beam, h, true).next!);
  }
  return beams[0] ?? null;
}

/** Each layer takes its own hinge from all of them (the author's choice,
 * 2026-11-20, over a direction turning in paint order). */
export function chooseHinges(layout: AxisLayout, width = 48): Hinge[] {
  const all = allHinges();
  return beamSearch(scoreContext(layout), () => all, width)?.hinges ?? layout.facts.map(() => ({ flat: true }) as Hinge);
}

/** A hinge described for the GLB. */
export function describeHinge(h: Hinge): Record<string, unknown> {
  return h.flat ? { flat: true } : { rises: ['right', 'up-right', 'up', 'up-left', 'left', 'down-left', 'down', 'down-right'][h.dir], line: `${h.pos}/4`, part: FRACTIONS[h.frac] };
}

/** The views where a layer's leaf, at its centroid, shows a light; the one
 * nearest the front first. For sway and for turning to a selected layer. */
export function glintViews(lights: readonly RectLight[], point: [number, number, number], plane: GlassPlane, limit = 40, step = 2): { az: number; el: number }[] {
  const found: { az: number; el: number; angle: number }[] = [];
  for (let el = -limit; el <= limit; el += step) for (let az = -limit; az <= limit; az += step) {
    const dir = viewDirection(az, el), angle = Math.acos(Math.min(1, dir[2])) / DEG;
    if (angle < 10 || angle > limit) continue;
    if (glints(lights, point, plane.gx, plane.gy, dir)) found.push({ az, el, angle });
  }
  return found.sort((a, b) => a.angle - b.angle || a.el - b.el || a.az - b.az);
}
