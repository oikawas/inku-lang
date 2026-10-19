import { CanvasTexture, DoubleSide, Mesh, MeshBasicMaterial, PlaneGeometry, SRGBColorSpace } from 'three';
import type { XY } from '../scene/types';
import { rasterSizedSvg } from './circleAppearance';

/** Keep the shared painter's abstract presence behind the solids, without
 * inventing physical shapes or omitting the saved layer. */
export async function preparePresence(svg: string, canvas: XY) {
  const raster = document.createElement('canvas');
  const scale = 1024 / Math.max(...canvas);
  raster.width = Math.max(1, Math.ceil(canvas[0] * scale));
  raster.height = Math.max(1, Math.ceil(canvas[1] * scale));
  const context = raster.getContext('2d');
  if (!context) throw new Error('presence_raster_unavailable');
  const url = URL.createObjectURL(new Blob([rasterSizedSvg(svg, raster.width, raster.height)], { type: 'image/svg+xml' }));
  const image = new Image();
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    await new Promise<void>((resolve, reject) => {
      timer = setTimeout(() => reject(new Error('presence_decode_timeout')), 5000);
      image.onload = () => resolve(); image.onerror = () => reject(new Error('presence_decode_failed'));
      image.src = url;
    });
    context.drawImage(image, 0, 0, raster.width, raster.height);
  } finally {
    clearTimeout(timer); image.onload = null; image.onerror = null;
    image.src = ''; URL.revokeObjectURL(url);
  }
  const texture = new CanvasTexture(raster); texture.colorSpace = SRGBColorSpace; texture.generateMipmaps = false;
  const material = new MeshBasicMaterial({ map: texture, transparent: true, depthWrite: false,
    side: DoubleSide, toneMapped: false });
  const mesh = new Mesh(new PlaneGeometry(...canvas), material);
  mesh.name = 'Presence layer'; mesh.userData = { role: 'presence', representation: 'shared-painter-plane' };
  return { mesh, dispose() { mesh.geometry.dispose(); material.dispose(); texture.dispose(); raster.width = raster.height = 1; } };
}
