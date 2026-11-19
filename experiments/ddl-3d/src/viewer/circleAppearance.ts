import {
  BufferGeometry, ClampToEdgeWrapping, DataTexture, Float32BufferAttribute, FrontSide, LinearFilter,
  Mesh, MeshLambertMaterial, RGBAFormat, SRGBColorSpace, Uint32BufferAttribute, UnsignedByteType, Vector3,
} from 'three';
import type { MeshPacket, XY } from '../scene/types.ts';
import { shadeSolid, type SolidUniforms } from './solidShading.ts';

export interface PaintAppearanceResources {
  texture: DataTexture;
  materials: MeshLambertMaterial[];
  dispose(): void;
}

const MAX_RASTER_SIDE = 1024;
const RAYS = 256;
/** The blurred colour a sphere turns to: the paint at about this many texels across. */
const BLUR_SIDE = 16;

/** Give the root <svg> the raster's pixel size, keeping its viewBox. WebKit
 * otherwise runs the filters at the SVG's own, larger size before scaling. */
export function rasterSizedSvg(svg: string, width: number, height: number): string {
  const root = /<svg[\s>]/.exec(svg);
  if (!root) return svg;
  const end = svg.indexOf('>', root.index);
  if (end < 0) return svg;
  const tag = svg.slice(root.index, end);
  const size = /\s(width|height)\s*=\s*("[^"]*"|'[^']*')/g;
  if ((tag.match(size) ?? []).length !== 2) return svg;
  const sized = tag.replace(size, (_, name: string) => ` ${name}="${name === 'width' ? width : height}"`);
  return svg.slice(0, root.index) + sized + svg.slice(end);
}

/** The outer painted radius, including sparse brush fringe, on each radial ray. */
export function paintedRadii(data: Uint8ClampedArray, width: number, height: number,
  bounds: [number, number, number, number], center: XY): Float64Array {
  const radii = new Float64Array(RAYS);
  for (let y = 0; y < height; y++) for (let x = 0; x < width; x++) {
    if (data[(y * width + x) * 4 + 3] < 2) continue;
    const dx = bounds[0] + (x + 0.5) / width * bounds[2] - center[0];
    const dy = bounds[1] + (y + 0.5) / height * bounds[3] - center[1];
    const angle = (Math.atan2(dy, dx) + Math.PI * 2) % (Math.PI * 2);
    const bin = Math.floor(angle / (Math.PI * 2) * RAYS) % RAYS;
    // A pixel has area; retain its outward half diagonal at the silhouette.
    radii[bin] = Math.max(radii[bin], Math.hypot(dx, dy) + Math.hypot(bounds[2] / width, bounds[3] / height) / 2);
  }
  const supported = Array.from(radii.keys()).filter(index => radii[index] > 0);
  if (!supported.length) return radii;
  // A small raster can have fewer edge pixels than rays. Interpolate the empty
  // angular bins before adding a narrow envelope for the sphere's tessellation.
  for (let bin = 0; bin < RAYS; bin++) {
    if (radii[bin]) continue;
    let before = 1, after = 1;
    while (!radii[(bin + RAYS - before) % RAYS]) before++;
    while (!radii[(bin + after) % RAYS]) after++;
    radii[bin] = (radii[(bin + RAYS - before) % RAYS] * after + radii[(bin + after) % RAYS] * before) / (before + after);
  }
  return radii.map((_, bin) => Math.max(...[-3, -2, -1, 0, 1, 2, 3].map(offset => radii[(bin + RAYS + offset) % RAYS])));
}

/** The paint's colour spread into its transparent pixels (push-pull), so a
 * wall or a sphere's back never samples empty fringe. Alpha stays the
 * paint's own. Rows run bottom to top, as a texture reads them. `blur` is the
 * same colour at about 16 texels across, opaque. An empty raster takes `color`. */
export function extendColor(data: Uint8ClampedArray, width: number, height: number, color: string) {
  type Level = { w: number; h: number; c: Float32Array };
  // Premultiplied colour and coverage, level by level down to one texel.
  const first = new Float32Array(width * height * 4);
  for (let i = 0; i < width * height; i++) {
    const a = data[i * 4 + 3] / 255;
    first[i * 4] = data[i * 4] / 255 * a; first[i * 4 + 1] = data[i * 4 + 1] / 255 * a; first[i * 4 + 2] = data[i * 4 + 2] / 255 * a; first[i * 4 + 3] = a;
  }
  const levels: Level[] = [{ w: width, h: height, c: first }];
  while (levels.at(-1)!.w > 1 || levels.at(-1)!.h > 1) {
    const { w, h, c } = levels.at(-1)!, w2 = Math.ceil(w / 2), h2 = Math.ceil(h / 2), next = new Float32Array(w2 * h2 * 4);
    for (let y = 0; y < h2; y++) for (let x = 0; x < w2; x++) {
      let n = 0;
      for (const [dx, dy] of [[0, 0], [1, 0], [0, 1], [1, 1]]) {
        const sx = 2 * x + dx, sy = 2 * y + dy; if (sx >= w || sy >= h) continue;
        for (let k = 0; k < 4; k++) next[(y * w2 + x) * 4 + k] += c[(sy * w + sx) * 4 + k]; n++;
      }
      for (let k = 0; k < 4; k++) next[(y * w2 + x) * 4 + k] /= n;
    }
    levels.push({ w: w2, h: h2, c: next });
  }
  // Pull: each level is laid over the filled level above it, coarsest first.
  const top = levels.at(-1)!.c, rgb = [1, 3, 5].map(o => parseInt(color.slice(o, o + 2), 16) / 255);
  if (top[3] < 1e-6) { top.set([...rgb, 1]); } else { for (let k = 0; k < 3; k++) top[k] /= top[3]; top[3] = 1; }
  let blur: Level = levels.at(-1)!;
  for (let l = levels.length - 2; l >= 0; l--) {
    const { w, h, c } = levels[l], up = levels[l + 1];
    for (let y = 0; y < h; y++) for (let x = 0; x < w; x++) {
      const i = (y * w + x) * 4, j = ((y >> 1) * up.w + (x >> 1)) * 4, rest = 1 - c[i + 3];
      for (let k = 0; k < 3; k++) c[i + k] += rest * up.c[j + k];
      c[i + 3] = 1;
    }
    if (Math.max(w, h) <= BLUR_SIDE) blur = levels[l];
  }
  const bytes = (level: Level, alpha: Uint8ClampedArray | null) => {
    const out = new Uint8Array(level.w * level.h * 4);
    for (let y = 0; y < level.h; y++) for (let x = 0; x < level.w; x++) {
      const from = (y * level.w + x) * 4, to = ((level.h - 1 - y) * level.w + x) * 4;
      for (let k = 0; k < 3; k++) out[to + k] = Math.round(Math.min(1, Math.max(0, level.c[from + k])) * 255);
      out[to + 3] = alpha ? alpha[from + 3] : 255;
    }
    return out;
  };
  return { filled: bytes(levels[0], data), blur: { data: bytes(blur, null), width: blur.w, height: blur.h } };
}

/** One set of canvas UVs for every face of a painted solid, and `surf` for
 * the shader (x: 1 on a wall; y: a sphere's height, -1 back to 1 front, or 2).
 * A cap maps the paper straight on. A wall folds back in from its edge, like
 * a canvas wrapped round a frame: at depth t of thickness T it samples the
 * paint min(t, T − t) inside the edge, so front and back edges meet the cap's
 * own texel and the wall carries the paint's grain. A source vertex is shared
 * by every triangle that maps it the same way. */
export function mapPaintSurfaces(geometry: BufferGeometry, bounds: [number, number, number, number],
  canvas: XY, options: { walls: boolean; round: boolean; filled: boolean; texel: number }): BufferGeometry {
  geometry.computeBoundingBox();
  const box = geometry.boundingBox!, size = box.max.clone().sub(box.min);
  const positions = geometry.getAttribute('position'), normals = geometry.getAttribute('normal');
  const index = geometry.index, corners = index ? index.count : positions.count;
  const source = (corner: number) => index ? index.getX(corner) : corner;
  const mapped = new Map<number, number>(), order: number[] = [], walls: boolean[] = [];
  const triangles = new Uint32Array(corners);
  const a = new Vector3(), b = new Vector3(), c = new Vector3();
  for (let i = 0; i < corners; i += 3) {
    a.fromBufferAttribute(positions, source(i)); b.fromBufferAttribute(positions, source(i + 1)); c.fromBufferAttribute(positions, source(i + 2));
    const normal = b.sub(a).cross(c.sub(a)).normalize();
    const wall = options.walls && !options.round && Math.abs(normal.z) < 0.5;
    for (let j = i; j < i + 3; j++) {
      const key = source(j) * 2 + (wall ? 1 : 0);
      let vertex = mapped.get(key);
      if (vertex === undefined) { vertex = order.length; mapped.set(key, vertex); order.push(source(j)); walls.push(wall); }
      triangles[j] = vertex;
    }
  }
  const position = new Float32Array(order.length * 3), normal = new Float32Array(order.length * 3);
  const uv = new Float32Array(order.length * 2), surf = new Float32Array(order.length * 2);
  const half = Math.max(1e-8, Math.max(Math.abs(box.max.z), Math.abs(box.min.z)));
  order.forEach((vertex, k) => {
    let x = positions.getX(vertex), y = positions.getY(vertex);
    const z = positions.getZ(vertex);
    position.set([x, y, z], k * 3);
    if (normals) normal.set([normals.getX(vertex), normals.getY(vertex), normals.getZ(vertex)], k * 3);
    if (walls[k] && normals) {
      const nx = normals.getX(vertex), ny = normals.getY(vertex), length = Math.hypot(nx, ny);
      const t = box.max.z - z, inside = Math.min(t, size.z - t) + 1.5 * options.texel;
      if (length > 1e-6) { x -= nx / length * inside; y -= ny / length * inside; }
    }
    uv[k * 2] = (x + canvas[0] / 2 - bounds[0]) / bounds[2];
    uv[k * 2 + 1] = 1 - (canvas[1] / 2 - y - bounds[1]) / bounds[3];
    surf[k * 2] = walls[k] ? 1 : 0;
    surf[k * 2 + 1] = options.round && options.filled ? z / half : 2;
  });
  const result = new BufferGeometry();
  result.setAttribute('position', new Float32BufferAttribute(position, 3));
  if (normals) result.setAttribute('normal', new Float32BufferAttribute(normal, 3));
  result.setAttribute('uv', new Float32BufferAttribute(uv, 2));
  result.setAttribute('surf', new Float32BufferAttribute(surf, 2));
  result.setIndex(new Uint32BufferAttribute(triangles, 1));
  result.boundingBox = box.clone();
  return result;
}

/** A mark's decoded paint, its colour spread for walls and spheres, not yet given to its mesh. */
export interface PaintRaster {
  pixels: ImageData;
  filled: Uint8Array;
  blur: { data: Uint8Array; width: number; height: number };
  dispose(): void;
}

/** Rasterize the shared SVG filters once. Nothing here touches the mesh. */
export async function rasterizePaint(packet: MeshPacket, maxSize = MAX_RASTER_SIDE): Promise<PaintRaster | null> {
  const appearance = packet.appearance;
  if (!appearance) return null;
  const { bounds, svg } = appearance;
  if (!Number.isFinite(maxSize) || maxSize < 3) throw new Error('invalid_circle_raster_budget');
  const limit = Math.min(MAX_RASTER_SIDE, Math.floor(maxSize));
  const scale = Math.min(1, limit / Math.max(bounds[2], bounds[3]) / 1024);
  const width = Math.max(3, Math.ceil(bounds[2] * 1024 * scale));
  const height = Math.max(3, Math.ceil(bounds[3] * 1024 * scale));
  const raster = document.createElement('canvas');
  raster.width = width; raster.height = height;
  const context = raster.getContext('2d', { willReadFrequently: true });
  if (!context) throw new Error('circle_raster_unavailable');
  const url = URL.createObjectURL(new Blob([rasterSizedSvg(svg, width, height)], { type: 'image/svg+xml' }));
  const image = new Image();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await new Promise<void>((resolve, reject) => {
      timer = setTimeout(() => reject(new Error('circle_appearance_timeout')), 5000);
      image.onload = () => resolve();
      image.onerror = () => reject(new Error('circle_appearance_decode_failed'));
      image.src = url;
    });
    context.drawImage(image, 0, 0, width, height);
  } finally {
    clearTimeout(timer); image.onload = null; image.onerror = null;
    image.src = ''; URL.revokeObjectURL(url);
  }
  // ClampToEdge must sample transparent pixels outside the crop, including
  // where an unusually wide brush reaches the conservative SVG bounds.
  context.clearRect(0, 0, width, 1); context.clearRect(0, height - 1, width, 1);
  context.clearRect(0, 0, 1, height); context.clearRect(width - 1, 0, 1, height);
  const pixels = context.getImageData(0, 0, width, height);
  raster.width = raster.height = 1;
  const { filled, blur } = extendColor(pixels.data, width, height, packet.color);
  return { pixels, filled, blur, dispose() { /* Plain arrays; nothing to release. */ } };
}

/** Fit the solid to the decoded paint and give it one lit, painted material. */
export function applyPaint(mesh: Mesh, packet: MeshPacket, canvas: XY, painted: PaintRaster, shared: SolidUniforms): PaintAppearanceResources {
  const { bounds, center } = packet.appearance!;
  const { pixels, filled, blur } = painted, { width, height } = pixels;
  const round = packet.primitive === 'circle' || packet.primitive === 'ellipse';
  const radii = round ? paintedRadii(pixels.data, width, height, bounds, center) : null;
  const positions = mesh.geometry.getAttribute('position');
  let depth = 0;
  for (let i = 0; i < positions.count; i++) depth = Math.max(depth, Math.abs(positions.getZ(i)));
  for (let i = 0; i < positions.count; i++) {
    let x = positions.getX(i) + canvas[0] / 2;
    let y = canvas[1] / 2 - positions.getY(i);
    const dx = x - center[0], dy = y - center[1], distance = Math.hypot(dx, dy);
    const rho = depth > 0 ? Math.sqrt(Math.max(0, 1 - (positions.getZ(i) / depth) ** 2)) : 0;
    if (radii && distance > 1e-8 && rho > 1e-5) {
      const angle = ((Math.atan2(dy, dx) + Math.PI * 2) % (Math.PI * 2)) / (Math.PI * 2) * RAYS;
      const bin = Math.floor(angle), fraction = angle - bin;
      const outer = radii[bin] * (1 - fraction) + radii[(bin + 1) % RAYS] * fraction;
      // A fully clipped ray has no painted support; alpha removes its surface.
      if (outer > 0) {
        x = center[0] + dx / distance * outer * rho;
        y = center[1] + dy / distance * outer * rho;
        positions.setXY(i, x - canvas[0] / 2, canvas[1] / 2 - y);
      }
    }
  }
  positions.needsUpdate = true;
  // A round keeps the ellipsoid's own normals: normals taken again from the
  // stepped painted outline would crease along the meridians in the light.
  if (!round) mesh.geometry.computeVertexNormals();
  mesh.geometry.computeBoundingBox(); mesh.geometry.computeBoundingSphere();
  const previous = mesh.geometry;
  mesh.geometry = mapPaintSurfaces(previous, bounds, canvas, {
    walls: packet.filled === true || (!round && ['line', 'free_line', 'arc'].includes(packet.primitive)),
    round, filled: packet.filled === true, texel: Math.max(bounds[2] / width, bounds[3] / height),
  });
  if (mesh.geometry !== previous) previous.dispose();
  const texture = new DataTexture(filled, width, height, RGBAFormat, UnsignedByteType);
  const blurTexture = new DataTexture(blur.data, blur.width, blur.height, RGBAFormat, UnsignedByteType);
  for (const map of [texture, blurTexture]) {
    map.colorSpace = SRGBColorSpace; map.wrapS = map.wrapT = ClampToEdgeWrapping;
    map.magFilter = map.minFilter = LinearFilter; map.generateMipmaps = false; map.needsUpdate = true;
  }
  const material = new MeshLambertMaterial({ map: texture, color: 0xffffff, opacity: 1,
    transparent: true, alphaTest: 1 / 255, side: FrontSide });
  shadeSolid(material, shared, { blur: blurTexture, wallOpacity: packet.opacity });
  mesh.material = material;
  return { texture, materials: [material], dispose() {
    texture.dispose(); blurTexture.dispose(); material.dispose(); painted.dispose();
  } };
}
