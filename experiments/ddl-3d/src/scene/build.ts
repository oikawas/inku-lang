import {
  BufferGeometry, Float32BufferAttribute, Uint32BufferAttribute, SphereGeometry,
  Shape, ExtrudeGeometry, Matrix4, Vector3, EdgesGeometry, MeshBasicMaterial,
} from 'three';
import { mergeGeometries } from 'three/addons/utils/BufferGeometryUtils.js';
import { Brush, Evaluator, INTERSECTION } from 'three-bvh-csg';
import type { XY, GeometryMark, PreparedScene, MeshPacket, ScenePacket } from './types.ts';

const MAX_TRIANGLES = 500_000;
const MAX_BYTES = 128 * 1024 * 1024;
const EPS = 1e-8;
const finite = (v: number) => Number.isFinite(v) && Math.abs(v) < 1000;
const validPoint = (p: XY) => p.length === 2 && p.every(finite);
const distance = (a: XY, b: XY) => Math.hypot(a[0] - b[0], a[1] - b[1]);

function clean(points: XY[], closed = false): XY[] {
  if (points.length > 8192 || points.some(p => !validPoint(p))) throw new Error('invalid_or_excessive_contour');
  const result = points.filter((p, i) => i === 0 || distance(p, points[i - 1]) > EPS);
  if (closed && result.length > 2 && distance(result[0], result.at(-1)!) < EPS) result.pop();
  if (result.length < (closed ? 3 : 2)) throw new Error('degenerate_geometry');
  return result;
}

function attributes(geometry: BufferGeometry): BufferGeometry {
  for (const key of Object.keys(geometry.attributes)) if (key !== 'position' && key !== 'normal') geometry.deleteAttribute(key);
  geometry.clearGroups();
  if (!geometry.getAttribute('normal')) geometry.computeVertexNormals();
  return geometry;
}

function combine(parts: BufferGeometry[]): BufferGeometry {
  if (!parts.length) throw new Error('empty_geometry');
  const source = parts.map(g => attributes(g.index ? g.toNonIndexed() : g));
  const merged = mergeGeometries(source, false);
  for (const geometry of new Set([...parts, ...source])) geometry.dispose();
  if (!merged) throw new Error('geometry_merge_failed');
  return merged;
}

/** A closed tube around a polyline. Its circular section has no end holes. */
function tube(points: Vector3[], radius: number, closed = false, sides = 6): BufferGeometry {
  const positions: number[] = [], indices: number[] = [];
  const n = points.length;
  if (n < 2 || n > 8192 || !(radius > 0 && finite(radius))) throw new Error('invalid_tube');
  // Parallel-transported frames also work for the sphere's latitude/longitude rings.
  let normal = new Vector3(0, 0, 1);
  for (let i = 0; i < n; i++) {
    const previous = points[closed ? (i + n - 1) % n : Math.max(0, i - 1)];
    const next = points[closed ? (i + 1) % n : Math.min(n - 1, i + 1)];
    const tangent = next.clone().sub(previous).normalize();
    if (Math.abs(tangent.dot(normal)) > 0.98) normal = new Vector3(0, 1, 0);
    const binormal = tangent.clone().cross(normal).normalize();
    normal = binormal.clone().cross(tangent).normalize();
    for (let j = 0; j < sides; j++) {
      const theta = 2 * Math.PI * j / sides;
      const p = points[i].clone().addScaledVector(normal, radius * Math.cos(theta)).addScaledVector(binormal, radius * Math.sin(theta));
      positions.push(p.x, p.y, p.z);
    }
  }
  for (let i = 0; i < (closed ? n : n - 1); i++) {
    for (let j = 0; j < sides; j++) {
      const a = i * sides + j, b = i * sides + (j + 1) % sides;
      const c = ((i + 1) % n) * sides + j, d = ((i + 1) % n) * sides + (j + 1) % sides;
      indices.push(a, b, c, b, d, c);
    }
  }
  if (!closed) {
    positions.push(...points[0].toArray(), ...points[n - 1].toArray());
    for (let j = 0; j < sides; j++) {
      indices.push(n * sides, (j + 1) % sides, j);
      indices.push(n * sides + 1, (n - 1) * sides + j, (n - 1) * sides + (j + 1) % sides);
    }
  }
  const result = new BufferGeometry();
  result.setAttribute('position', new Float32BufferAttribute(positions, 3));
  result.setIndex(indices);
  result.computeVertexNormals();
  return result;
}

/** Segment dash lengths in source units, carrying phase across every vertex. */
export function dashedPaths(points: XY[], pattern: number[]): XY[][] {
  if (!pattern.length) return [points];
  if (pattern.length > 16 || pattern.some(n => !finite(n) || n <= 0)) throw new Error('invalid_dash');
  const parts: XY[][] = [];
  let phase = 0, remaining = pattern[0], current: XY[] = [points[0]];
  for (let i = 1; i < points.length; i++) {
    let start = points[i - 1];
    const end = points[i];
    let length = distance(start, end);
    while (length > EPS) {
      if (parts.length > 8192) throw new Error('dash_budget_exceeded');
      const step = Math.min(length, remaining), t = step / length;
      const stop: XY = [start[0] + (end[0] - start[0]) * t, start[1] + (end[1] - start[1]) * t];
      if (phase % 2 === 0) current.push(stop);
      remaining -= step;
      if (remaining < EPS) {
        if (phase % 2 === 0 && current.length > 1) parts.push(current);
        phase = (phase + 1) % pattern.length; remaining = pattern[phase]; current = [stop];
      }
      start = stop; length -= step;
    }
  }
  if (phase % 2 === 0 && current.length > 1) parts.push(current);
  return parts;
}

function prism(points: XY[], depth?: number): BufferGeometry {
  const contour = clean(points, true);
  const bounds = extent(contour);
  const thickness = depth ?? Math.min(bounds[0], bounds[1]);
  if (!(thickness > EPS && finite(thickness))) throw new Error('degenerate_geometry');
  const shape = new Shape();
  shape.moveTo(...contour[0]);
  for (const point of contour.slice(1)) shape.lineTo(...point);
  shape.closePath();
  return attributes(new ExtrudeGeometry(shape, { depth: thickness, bevelEnabled: false, steps: 1 }).translate(0, 0, -thickness / 2));
}

function extent(points: XY[]): XY {
  return [Math.max(...points.map(p => p[0])) - Math.min(...points.map(p => p[0])),
    Math.max(...points.map(p => p[1])) - Math.min(...points.map(p => p[1]))];
}

function pyramid(points: XY[]): BufferGeometry {
  const p = clean(points, true);
  const depth = Math.min(...extent(p));
  const center: XY = [p.reduce((n, v) => n + v[0], 0) / 3, p.reduce((n, v) => n + v[1], 0) / 3];
  const vertices = p.map(v => new Vector3(...v, depth / 2));
  vertices.push(new Vector3(...center, -depth / 2));
  const faces = [[0, 1, 2], [0, 3, 1], [1, 3, 2], [2, 3, 0]];
  const centroid = new Vector3(...center, depth / 4);
  const flat: number[] = [];
  for (let [a, b, c] of faces) {
    const normal = vertices[b].clone().sub(vertices[a]).cross(vertices[c].clone().sub(vertices[a]));
    if (normal.dot(vertices[a].clone().sub(centroid)) < 0) [b, c] = [c, b];
    flat.push(...vertices[a].toArray(), ...vertices[b].toArray(), ...vertices[c].toArray());
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(flat, 3));
  geometry.computeVertexNormals();
  return geometry;
}

function cloud(points: XY[]): BufferGeometry {
  // The core's radial contour stays intact at Z=0. Rings shrink toward both poles.
  const p = clean(points, true), depth = Math.min(...extent(p));
  const cx = p.reduce((s, v) => s + v[0], 0) / p.length, cy = p.reduce((s, v) => s + v[1], 0) / p.length;
  const positions: number[] = [], indices: number[] = [];
  // Orient outward before creating consistently wound rings.
  const area = p.reduce((s, v, i) => s + v[0] * p[(i + 1) % p.length][1] - p[(i + 1) % p.length][0] * v[1], 0);
  if (area < 0) p.reverse();
  for (let r = 1; r < 8; r++) {
    const angle = -Math.PI / 2 + r * Math.PI / 8;
    for (const v of p) positions.push(cx + (v[0] - cx) * Math.cos(angle), cy + (v[1] - cy) * Math.cos(angle), depth / 2 * Math.sin(angle));
  }
  for (let r = 0; r < 6; r++) for (let i = 0; i < p.length; i++) {
    const a = r * p.length + i, b = r * p.length + (i + 1) % p.length, c = a + p.length, d = b + p.length;
    indices.push(a, b, c, b, d, c);
  }
  positions.push(cx, cy, -depth / 2, cx, cy, depth / 2);
  for (let i = 0; i < p.length; i++) {
    indices.push(7 * p.length, (i + 1) % p.length, i);
    indices.push(7 * p.length + 1, 6 * p.length + i, 6 * p.length + (i + 1) % p.length);
  }
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(positions, 3)); geometry.setIndex(indices); geometry.computeVertexNormals();
  return attributes(geometry);
}

function stroke3d(points: Vector3[], width: number, pattern: number[], closed = false): BufferGeometry {
  if (!pattern.length) return tube(points, width / 2, closed);
  if (pattern.some(v => !finite(v) || v <= 0) || pattern.length > 16) throw new Error('invalid_dash');
  if (closed) points = [...points, points[0]];
  const parts: BufferGeometry[] = [];
  let phase = 0, remaining = pattern[0], current = [points[0]];
  for (let i = 1; i < points.length; i++) {
    let start = points[i - 1], length = start.distanceTo(points[i]);
    while (length > EPS) {
      if (parts.length > 8192) throw new Error('dash_budget_exceeded');
      const step = Math.min(length, remaining), end = start.clone().lerp(points[i], step / length);
      if (phase % 2 === 0) current.push(end);
      remaining -= step;
      if (remaining < EPS) {
        if (phase % 2 === 0 && current.length > 1) parts.push(tube(current, width / 2));
        phase = (phase + 1) % pattern.length; remaining = pattern[phase]; current = [end];
      }
      start = end; length -= step;
    }
  }
  if (phase % 2 === 0 && current.length > 1) parts.push(tube(current, width / 2));
  return combine(parts);
}

function roundOutline(center: XY, radii: XY, width: number, dash: number[]): BufferGeometry {
  const parts: BufferGeometry[] = [], rz = Math.min(...radii);
  const ring = (fn: (angle: number) => Vector3) => parts.push(stroke3d(Array.from({ length: 32 }, (_, i) => fn(i * Math.PI / 16)), width, dash, true));
  for (const latitude of [-Math.PI / 4, 0, Math.PI / 4]) {
    ring(a => new Vector3(center[0] + radii[0] * Math.cos(latitude) * Math.cos(a), center[1] + radii[1] * Math.cos(latitude) * Math.sin(a), rz * Math.sin(latitude)));
  }
  for (let longitude = 0; longitude < Math.PI - EPS; longitude += Math.PI / 3) {
    ring(a => new Vector3(center[0] + radii[0] * Math.cos(a) * Math.cos(longitude), center[1] + radii[1] * Math.cos(a) * Math.sin(longitude), rz * Math.sin(a)));
  }
  return combine(parts);
}

function localGeometry(mark: GeometryMark): BufferGeometry {
  const { shape, width } = mark;
  if (!(width > 0 && finite(width))) throw new Error('invalid_width');
  if (shape.kind === 'round') {
    if (!validPoint(shape.center) || !validPoint(shape.radii) || shape.radii.some(v => v <= 0)) throw new Error('invalid_round');
    if (!mark.filled) return roundOutline(shape.center, shape.radii, width, mark.dash);
    return attributes(new SphereGeometry(1, 24, 16).scale(...shape.radii, Math.min(...shape.radii)).translate(...shape.center, 0));
  }
  const points = clean(shape.points, shape.kind === 'contour');
  if (shape.kind === 'path') {
    return combine(dashedPaths(points, mark.dash).map(path => tube(path.map(p => new Vector3(...p, 0)), width / 2)));
  }
  const solid = mark.primitive === 'triangle' ? pyramid(points) : mark.primitive === 'cloudform' ? cloud(points) : prism(points);
  if (mark.filled) return solid;
  const edges = new EdgesGeometry(solid, 28), positions = edges.getAttribute('position');
  const parts: BufferGeometry[] = [];
  for (let i = 0; i < positions.count; i += 2) {
    const a = new Vector3().fromBufferAttribute(positions, i), b = new Vector3().fromBufferAttribute(positions, i + 1);
    if (a.distanceTo(b) > EPS) parts.push(stroke3d([a, b], width, mark.dash));
  }
  edges.dispose(); solid.dispose();
  return combine(parts);
}

/** Canvas Y points down; reverse triangle winding when this affine reflects it. */
function world(geometry: BufferGeometry, transform: number[], canvas: XY): BufferGeometry {
  if (transform.length !== 6 || !transform.every(finite)) throw new Error('invalid_transform');
  const [a, b, c, d, e, f] = transform;
  const sum = a*a + b*b + c*c + d*d, det = a*d - b*c;
  const zScale = Math.sqrt(Math.max(0, (sum - Math.sqrt(Math.max(0, sum*sum - 4*det*det))) / 2));
  const matrix = new Matrix4().set(a, c, 0, e - canvas[0] / 2, -b, -d, 0, canvas[1] / 2 - f, 0, 0, zScale, 0, 0, 0, 0, 1);
  if (Math.abs(matrix.determinant()) < EPS) throw new Error('singular_transform');
  geometry.applyMatrix4(matrix);
  if (matrix.determinant() < 0) {
    const count = geometry.getAttribute('position').count;
    const index = geometry.index ? Array.from(geometry.index.array) : Array.from({ length: count }, (_, i) => i);
    for (let i = 0; i < index.length; i += 3) [index[i + 1], index[i + 2]] = [index[i + 2], index[i + 1]];
    geometry.setIndex(index);
  }
  return geometry;
}

function clip(geometry: BufferGeometry, contours: XY[][], canvas: XY): BufferGeometry {
  if (contours.length > 32) throw new Error('clip_depth_exceeded');
  const evaluator = new Evaluator();
  evaluator.attributes = ['position', 'normal']; evaluator.useGroups = false;
  const material = new MeshBasicMaterial();
  try {
    for (const contour of contours) {
      geometry.computeBoundingBox();
      const depth = Math.max(32, 2 * Math.max(Math.abs(geometry.boundingBox!.min.z), Math.abs(geometry.boundingBox!.max.z)) + 2);
      const boundary = world(prism(contour, depth), [1, 0, 0, 1, 0, 0], canvas);
      const left = new Brush(geometry, material), right = new Brush(boundary, material);
      left.updateMatrixWorld(); right.updateMatrixWorld();
      const result = evaluator.evaluate(left, right, INTERSECTION);
      left.disposeCacheData(); right.disposeCacheData();
      geometry.dispose(); boundary.dispose(); geometry = attributes(result.geometry);
      if (!geometry.getAttribute('position').count) break;
      if ((geometry.index?.count ?? geometry.getAttribute('position').count) / 3 > MAX_TRIANGLES) throw new Error('triangle_budget_exceeded');
    }
    return geometry;
  } finally { material.dispose(); }
}

export function buildScene(input: PreparedScene): ScenePacket {
  const { scene } = input;
  if (scene.marks.length > 4096 || !validPoint(scene.canvas) || scene.canvas.some(v => v <= 0)) throw new Error('object_budget_exceeded');
  const output: ScenePacket = { ...input, meshes: [], canvas: scene.canvas, background: scene.background, ground: scene.ground, diagnostics: [...scene.diagnostics], recoveries: [...scene.recoveries],
    objectCount: scene.marks.length, triangles: 0, bytes: 0, clippedObjects: 0 };
  // Do not retain the expanded DTO in the worker reply.
  delete (output as ScenePacket & { scene?: unknown }).scene;
  const append = (geometry: BufferGeometry, mark: GeometryMark, role: MeshPacket['role']) => {
    try {
      if (mark.clips.length) geometry = clip(geometry, mark.clips, scene.canvas);
      const positions = new Float32Array(geometry.getAttribute('position').array);
      if (!positions.length) { if (role === 'object') output.clippedObjects++; return; }
      if (positions.some(v => !finite(v))) throw new Error('invalid_vertices');
      const normals = new Float32Array(geometry.getAttribute('normal').array);
      if (normals.some(v => !Number.isFinite(v))) throw new Error('invalid_normals');
      const indices = geometry.index ? new Uint32Array(geometry.index.array) : null;
      output.triangles += (indices?.length ?? positions.length / 3) / 3;
      output.bytes += positions.byteLength + normals.byteLength + (indices?.byteLength ?? 0);
      if (output.triangles > MAX_TRIANGLES || output.bytes > MAX_BYTES) throw new Error('mesh_budget_exceeded');
      output.meshes.push({ positions, normals, indices, color: mark.color, opacity: mark.opacity,
        sourceIndex: mark.sourceIndex, performedIndex: mark.performedIndex, instanceIndex: mark.instanceIndex, primitive: mark.primitive,
        role, ...(role === 'pair-fill' ? { relatedSourceIndex: mark.pairFill?.sourceIndex } : {}) });
    } finally { geometry.dispose(); }
  };
  for (const mark of scene.marks) {
    if (!/^#[0-9a-f]{6}$/i.test(mark.color) || !Number.isFinite(mark.opacity) || mark.opacity < 0 || mark.opacity > 1) throw new Error('invalid_material');
    append(world(localGeometry(mark), mark.transform, scene.canvas), mark, 'object');
    if (mark.pairFill) append(world(prism(mark.pairFill.points), [1, 0, 0, 1, 0, 0], scene.canvas),
      { ...mark, color: mark.pairFill.color, opacity: mark.pairFill.opacity }, 'pair-fill');
  }
  if (!output.meshes.length && !scene.ground) throw new Error('no_visible_geometry');
  return output;
}

export function unpackMesh(packet: MeshPacket): BufferGeometry {
  const geometry = new BufferGeometry();
  geometry.setAttribute('position', new Float32BufferAttribute(packet.positions, 3));
  geometry.setAttribute('normal', new Float32BufferAttribute(packet.normals, 3));
  if (packet.indices) geometry.setIndex(new Uint32BufferAttribute(packet.indices, 1));
  return geometry;
}
