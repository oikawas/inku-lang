import {
  BufferGeometry, CanvasTexture, ClampToEdgeWrapping, Float32BufferAttribute, FrontSide,
  Mesh, MeshBasicMaterial, SRGBColorSpace, Uint32BufferAttribute, Vector3,
} from 'three';
import type { MeshPacket, XY } from '../scene/types.ts';

export interface PaintAppearanceResources {
  texture: CanvasTexture;
  materials: MeshBasicMaterial[];
  dispose(): void;
}

const MAX_RASTER_SIDE = 1024;
const RAYS = 256;

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

/** A solid wall retains pigment where a filter makes the front transparent. */
export function sidePaintPixels(data: Uint8ClampedArray, color: string): Uint8ClampedArray {
  const output = new Uint8ClampedArray(data.length);
  const rgb = [1, 3, 5].map(offset => parseInt(color.slice(offset, offset + 2), 16));
  for (let i = 0; i < data.length; i += 4) {
    const alpha = data[i + 3] / 255;
    for (let channel = 0; channel < 3; channel++) {
      output[i + channel] = (alpha ? data[i + channel] : rgb[channel]) * (0.6 + 0.4 * alpha);
    }
    output[i + 3] = 255;
  }
  return output;
}

/** Caps retain canvas UVs; walls unfold Z across the same filtered paint.
 * A source vertex is shared by every triangle that maps it the same way. */
export function mapPaintSurfaces(geometry: BufferGeometry, bounds: [number, number, number, number],
  canvas: XY, walls: boolean): BufferGeometry {
  geometry.computeBoundingBox();
  const box = geometry.boundingBox!, size = box.max.clone().sub(box.min);
  const positions = geometry.getAttribute('position'), normals = geometry.getAttribute('normal');
  const index = geometry.index, corners = index ? index.count : positions.count;
  const source = (corner: number) => index ? index.getX(corner) : corner;
  // Cap, X-facing wall or Y-facing wall: each maps a source vertex to one UV.
  const mapped = new Map<number, number>(), order: number[] = [], faces: number[] = [];
  const triangles = new Uint32Array(corners);
  const a = new Vector3(), b = new Vector3(), c = new Vector3();
  const result = new BufferGeometry();
  let lastMaterial = -1, groupStart = 0;
  for (let i = 0; i < corners; i += 3) {
    a.fromBufferAttribute(positions, source(i)); b.fromBufferAttribute(positions, source(i + 1)); c.fromBufferAttribute(positions, source(i + 2));
    const normal = b.sub(a).cross(c.sub(a)).normalize();
    const wall = walls && Math.abs(normal.z) < 0.5;
    const material = wall ? 1 : 0, face = !wall ? 0 : Math.abs(normal.x) > Math.abs(normal.y) ? 1 : 2;
    if (material !== lastMaterial) {
      if (lastMaterial >= 0) result.addGroup(groupStart, i - groupStart, lastMaterial);
      lastMaterial = material; groupStart = i;
    }
    for (let j = i; j < i + 3; j++) {
      const key = source(j) * 3 + face;
      let vertex = mapped.get(key);
      if (vertex === undefined) { vertex = order.length; mapped.set(key, vertex); order.push(source(j)); faces.push(face); }
      triangles[j] = vertex;
    }
  }
  if (lastMaterial >= 0) result.addGroup(groupStart, corners - groupStart, lastMaterial);
  const position = new Float32Array(order.length * 3), normal = new Float32Array(order.length * 3), uv = new Float32Array(order.length * 2);
  order.forEach((vertex, k) => {
    const x = positions.getX(vertex), y = positions.getY(vertex), z = positions.getZ(vertex);
    position.set([x, y, z], k * 3);
    if (normals) normal.set([normals.getX(vertex), normals.getY(vertex), normals.getZ(vertex)], k * 3);
    let u = (x + canvas[0] / 2 - bounds[0]) / bounds[2];
    let v = 1 - (canvas[1] / 2 - y - bounds[1]) / bounds[3];
    const depth = (z - box.min.z) / Math.max(1e-8, size.z);
    if (faces[k] === 1) u = 0.15 + depth * 0.7;
    else if (faces[k] === 2) v = 0.15 + depth * 0.7;
    uv[k * 2] = u; uv[k * 2 + 1] = v;
  });
  result.setAttribute('position', new Float32BufferAttribute(position, 3));
  if (normals) result.setAttribute('normal', new Float32BufferAttribute(normal, 3));
  result.setAttribute('uv', new Float32BufferAttribute(uv, 2));
  result.setIndex(new Uint32BufferAttribute(triangles, 1));
  result.boundingBox = box.clone();
  return result;
}

/** Rasterize the shared SVG filters once, then paint caps and solid walls. */
export async function preparePaintAppearance(mesh: Mesh, packet: MeshPacket, canvas: XY, maxSize = MAX_RASTER_SIDE): Promise<PaintAppearanceResources | null> {
  const appearance = packet.appearance;
  if (!appearance) return null;
  const { bounds, center, svg } = appearance;
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
  mesh.geometry.computeVertexNormals(); mesh.geometry.computeBoundingBox(); mesh.geometry.computeBoundingSphere();
  const previous = mesh.geometry;
  mesh.geometry = mapPaintSurfaces(previous, bounds, canvas,
    packet.filled === true || (!round && ['line', 'free_line', 'arc'].includes(packet.primitive)));
  if (mesh.geometry !== previous) previous.dispose();
  const sideRaster = document.createElement('canvas');
  sideRaster.width = width; sideRaster.height = height;
  const sideContext = sideRaster.getContext('2d');
  if (!sideContext) throw new Error('paint_side_raster_unavailable');
  const sidePixels = sideContext.createImageData(width, height);
  sidePixels.data.set(sidePaintPixels(pixels.data, packet.color));
  sideContext.putImageData(sidePixels, 0, 0);
  const texture = new CanvasTexture(raster), sideTexture = new CanvasTexture(sideRaster);
  for (const map of [texture, sideTexture]) {
    map.colorSpace = SRGBColorSpace;
    map.wrapS = map.wrapT = ClampToEdgeWrapping;
    map.flipY = true; map.generateMipmaps = false;
  }
  const material = new MeshBasicMaterial({ map: texture, color: 0xffffff, opacity: 1,
    transparent: true, alphaTest: 1 / 255, side: FrontSide, toneMapped: false });
  const wall = new MeshBasicMaterial({ map: sideTexture, color: 0xffffff, opacity: packet.opacity,
    transparent: packet.opacity < 1, depthWrite: packet.opacity >= 1, side: FrontSide, toneMapped: false });
  const materials = [material, wall];
  mesh.material = materials;
  return { texture, materials, dispose() {
    texture.dispose(); sideTexture.dispose(); materials.forEach(m => m.dispose());
    raster.width = raster.height = sideRaster.width = sideRaster.height = 1;
  } };
}
