import {
  CanvasTexture, ClampToEdgeWrapping, Float32BufferAttribute, FrontSide,
  Mesh, MeshBasicMaterial, SRGBColorSpace,
} from 'three';
import type { MeshPacket, XY } from '../scene/types.ts';

export interface CircleAppearanceResources {
  texture: CanvasTexture;
  material: MeshBasicMaterial;
  dispose(): void;
}

const MAX_RASTER_SIDE = 1024;
const RAYS = 256;

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

/** Keep the sphere's Z volume while its equator follows the isolated 2D paint. */
export async function prepareCircleAppearance(mesh: Mesh, packet: MeshPacket, canvas: XY, maxSize = MAX_RASTER_SIDE): Promise<CircleAppearanceResources | null> {
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
  const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
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
  const radii = paintedRadii(context.getImageData(0, 0, width, height).data, width, height, bounds, center);
  const positions = mesh.geometry.getAttribute('position');
  const uv = new Float32Array(positions.count * 2);
  let depth = 0;
  for (let i = 0; i < positions.count; i++) depth = Math.max(depth, Math.abs(positions.getZ(i)));
  for (let i = 0; i < positions.count; i++) {
    let x = positions.getX(i) + canvas[0] / 2;
    let y = canvas[1] / 2 - positions.getY(i);
    const dx = x - center[0], dy = y - center[1], distance = Math.hypot(dx, dy);
    const rho = depth > 0 ? Math.sqrt(Math.max(0, 1 - (positions.getZ(i) / depth) ** 2)) : 0;
    if (distance > 1e-8 && rho > 1e-5) {
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
    uv[i * 2] = (x - bounds[0]) / bounds[2];
    // CanvasTexture flips the raster vertically during upload.
    uv[i * 2 + 1] = 1 - (y - bounds[1]) / bounds[3];
  }
  positions.needsUpdate = true;
  mesh.geometry.setAttribute('uv', new Float32BufferAttribute(uv, 2));
  mesh.geometry.computeVertexNormals(); mesh.geometry.computeBoundingBox(); mesh.geometry.computeBoundingSphere();
  const texture = new CanvasTexture(raster);
  texture.colorSpace = SRGBColorSpace;
  texture.wrapS = texture.wrapT = ClampToEdgeWrapping;
  texture.flipY = true;
  texture.generateMipmaps = false;
  const material = new MeshBasicMaterial({ map: texture, color: 0xffffff, opacity: 1,
    transparent: true, alphaTest: 1 / 255, side: FrontSide, toneMapped: false });
  mesh.material = material;
  return { texture, material, dispose() { texture.dispose(); material.dispose(); raster.width = raster.height = 1; } };
}
