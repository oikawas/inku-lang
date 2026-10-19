import type { GeometryMark, MeshPacket, XY } from './types.ts';

type Knot = { distance: number; node: number };
type Path = { mark: GeometryMark; local: XY[]; world: XY[]; distances: number[]; knots: Knot[] };
type Segment = { path: Path; index: number; box: number[] };
type Tree = { box: number[]; segments?: Segment[]; children?: Tree[] };
const length = (a: XY, b: XY) => Math.hypot(a[0] - b[0], a[1] - b[1]);
const lerp = (a: XY, b: XY, t: number): XY => [a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t];
const key = (value: { performedIndex: number; instanceIndex: number }) => `${value.performedIndex}:${value.instanceIndex}`;

function tree(segments: Segment[]): Tree {
  const box = [Math.min(...segments.map(s => s.box[0])), Math.min(...segments.map(s => s.box[1])),
    Math.max(...segments.map(s => s.box[2])), Math.max(...segments.map(s => s.box[3]))];
  if (segments.length <= 8) return { box, segments };
  const axis = box[2] - box[0] >= box[3] - box[1] ? 0 : 1;
  segments.sort((a, b) => a.box[axis] + a.box[axis + 2] - b.box[axis] - b.box[axis + 2]);
  const middle = Math.floor(segments.length / 2);
  return { box, children: [tree(segments.slice(0, middle)), tree(segments.slice(middle))] };
}

/** Only an endpoint can establish a joint; interior crossings remain separate. */
export function lineDepthLayout(marks: GeometryMark[], canvas: XY) {
  const tolerance = Math.min(...canvas) * 1e-7, parents: number[] = [];
  let pointCount = 0;
  const node = () => { const id = parents.length; parents.push(id); return id; };
  const root = (id: number): number => {
    while (parents[id] !== id) { parents[id] = parents[parents[id]]; id = parents[id]; }
    return id;
  };
  const paths: Path[] = marks.flatMap(mark => {
    if (mark.primitive !== 'line' || mark.shape.kind !== 'path' || mark.shape.points.length < 2) return [];
    pointCount += mark.shape.points.length;
    if (mark.shape.points.length > 8192 || pointCount > 50_000) throw new Error('mesh_budget_exceeded');
    const [a, b, c, d, e, f] = mark.transform;
    const local = mark.shape.points;
    const world = local.map(([x, y]): XY => [a*x + c*y + e - canvas[0]/2, canvas[1]/2 - b*x - d*y - f]);
    const distances = [0];
    for (let i = 1; i < world.length; i++) distances.push(distances[i - 1] + length(world[i - 1], world[i]));
    return [{ mark, local, world, distances, knots: [{ distance: 0, node: node() }, { distance: distances.at(-1)!, node: node() }] }];
  });
  const pins: { node: number; mark: GeometryMark }[] = [];
  // Other solids stay rigid. A line's endpoint follows the solid's own depth.
  const rigid = marks.filter(mark => mark.primitive !== 'line').map(mark => {
    const [a, b, c, d, e, f] = mark.transform, det = a*d - b*c;
    return { mark, contains(point: XY) {
      if (Math.abs(det) < 1e-8) return false;
      const x = point[0] + canvas[0]/2 - e, y = canvas[1]/2 - point[1] - f;
      const local: XY = [(d*x - c*y)/det, (-b*x + a*y)/det];
      const shape = mark.shape;
      if (shape.kind === 'round') {
        const dx = (local[0] - shape.center[0])/shape.radii[0], dy = (local[1] - shape.center[1])/shape.radii[1];
        return Math.abs(Math.hypot(dx, dy) - 1) * Math.min(...shape.radii) <= tolerance;
      }
      const points = shape.points, count = shape.kind === 'contour' ? points.length : points.length - 1;
      for (let i = 0; i < count; i++) {
        const start = points[i], end = points[(i + 1) % points.length], dx = end[0] - start[0], dy = end[1] - start[1];
        const t = Math.max(0, Math.min(1, ((local[0] - start[0])*dx + (local[1] - start[1])*dy) / Math.max(1e-20, dx*dx + dy*dy)));
        if (length(local, lerp(start, end, t)) <= tolerance) return true;
      }
      return false;
    } };
  });
  const segments = paths.flatMap(path => path.world.slice(1).map((end, i): Segment => {
    const start = path.world[i];
    return { path, index: i, box: [Math.min(start[0], end[0]), Math.min(start[1], end[1]), Math.max(start[0], end[0]), Math.max(start[1], end[1])] };
  }));
  const index = segments.length ? tree(segments) : null;
  const matches = (branch: Tree, point: XY, visit: (segment: Segment) => void) => {
    if (point[0] < branch.box[0] - tolerance || point[1] < branch.box[1] - tolerance
      || point[0] > branch.box[2] + tolerance || point[1] > branch.box[3] + tolerance) return;
    branch.segments?.forEach(visit);
    branch.children?.forEach(child => matches(child, point, visit));
  };
  for (const path of paths) for (const end of [0, 1]) {
    const point = end ? path.world.at(-1)! : path.world[0], endpoint = path.knots[end];
    for (const target of rigid) if (target.contains(point)) pins.push({ node: endpoint.node, mark: target.mark });
    if (!index) continue;
    matches(index, point, segment => {
      if (segment.path === path) return;
      const target = segment.path, i = segment.index, a = target.world[i], b = target.world[i + 1];
      const dx = b[0] - a[0], dy = b[1] - a[1], squared = dx*dx + dy*dy;
      if (!squared) return;
      const t = Math.max(0, Math.min(1, ((point[0] - a[0])*dx + (point[1] - a[1])*dy) / squared));
      if (length(point, lerp(a, b, t)) > tolerance) return;
      // Copies stacked along their own direction overlap rather than meet;
      // only their ends touching each other still join.
      const inside = (t > 0 || i > 0) && (t < 1 || i < target.world.length - 2);
      const next = end ? path.world.at(-2)! : path.world[1], ox = next[0] - point[0], oy = next[1] - point[1];
      if (inside && Math.abs(ox * dy - oy * dx) <= 1e-9 * Math.hypot(ox, oy) * Math.sqrt(squared)) return;
      const distance = target.distances[i] + t * Math.sqrt(squared);
      let knot = target.knots.find(k => Math.abs(k.distance - distance) <= tolerance);
      if (!knot) { knot = { distance, node: node() }; target.knots.push(knot); }
      parents[root(knot.node)] = root(endpoint.node);
    });
  }
  // Insert actual junctions before meshing, so a T junction can bend at its node.
  const expanded = new Map<GeometryMark, GeometryMark>();
  for (const path of paths) {
    path.knots.sort((a, b) => a.distance - b.distance);
    const distances = [...new Set([...path.distances, ...path.knots.map(k => k.distance)])].sort((a, b) => a - b);
    let i = 0;
    const local = distances.map(distance => {
      while (i < path.distances.length - 2 && path.distances[i + 1] < distance) i++;
      const t = (distance - path.distances[i]) / Math.max(1e-20, path.distances[i + 1] - path.distances[i]);
      return lerp(path.local[i], path.local[i + 1], t);
    });
    expanded.set(path.mark, { ...path.mark, shape: { kind: 'path', points: local } });
  }
  return {
    mark: (mark: GeometryMark) => expanded.get(mark) ?? mark,
    assign(meshes: MeshPacket[]) {
      const visible = new Map(meshes.filter(m => m.role === 'object').map(m => [key(m), m]));
      const members = new Map<number, Set<MeshPacket>>();
      for (const path of paths) {
        const mesh = visible.get(key(path.mark));
        if (!mesh) continue;
        for (const knot of path.knots) {
          const id = root(knot.node), values = members.get(id) ?? new Set<MeshPacket>();
          values.add(mesh); members.set(id, values);
        }
      }
      const fixed = new Map<number, Set<MeshPacket>>();
      for (const pin of pins) {
        const mesh = visible.get(key(pin.mark));
        if (!mesh) continue;
        const id = root(pin.node), values = fixed.get(id) ?? new Set<MeshPacket>();
        values.add(mesh); fixed.set(id, values);
      }
      const depths = new Map([...members].map(([id, values]) => {
        const targets = [...(fixed.get(id) ?? values)];
        return [id, targets.reduce((sum, mesh) => sum + mesh.layerZ, 0) / targets.length];
      }));
      for (const path of paths) {
        const mesh = visible.get(key(path.mark));
        if (!mesh || !path.knots.some(knot => (members.get(root(knot.node))?.size ?? 0) > 1 || fixed.has(root(knot.node)))) continue;
        const world = expanded.get(path.mark)!.shape;
        if (world.kind !== 'path') continue;
        const [a, b, c, d, e, f] = path.mark.transform;
        const points = world.points.map(([x, y]): XY => [a*x + c*y + e - canvas[0]/2, canvas[1]/2 - b*x - d*y - f]);
        let distance = 0, knot = 0;
        const values = points.map((point, i) => {
          if (i) distance += length(points[i - 1], point);
          while (knot < path.knots.length - 2 && path.knots[knot + 1].distance < distance - tolerance) knot++;
          const first = path.knots[knot], last = path.knots[knot + 1];
          const t = Math.max(0, Math.min(1, (distance - first.distance) / Math.max(1e-20, last.distance - first.distance)));
          return depths.get(root(first.node))! * (1 - t) + depths.get(root(last.node))! * t;
        });
        mesh.depthPath = { points, depths: values };
      }
    },
  };
}

/** Interpolate along the nearest centerline segment, including inserted joints. */
export function lineDepthAt(path: NonNullable<MeshPacket['depthPath']>, x: number, y: number): number {
  let nearest = Infinity, depth = path.depths[0];
  for (let i = 1; i < path.points.length; i++) {
    const a = path.points[i - 1], b = path.points[i], dx = b[0] - a[0], dy = b[1] - a[1];
    const t = Math.max(0, Math.min(1, ((x - a[0])*dx + (y - a[1])*dy) / Math.max(1e-20, dx*dx + dy*dy)));
    const squared = (x - a[0] - t*dx)**2 + (y - a[1] - t*dy)**2;
    if (squared < nearest) { nearest = squared; depth = path.depths[i - 1] * (1 - t) + path.depths[i] * t; }
  }
  return depth;
}
