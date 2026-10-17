import { CanvasTexture, EquirectangularReflectionMapping, SRGBColorSpace } from 'three';

export type Background = 'none' | 'support' | 'sky' | 'stars';

/** Local procedural skies: no network images, credentials, or saved-work changes. */
export function skyTexture(mode: 'sky' | 'stars'): CanvasTexture {
  const canvas = document.createElement('canvas'); canvas.width = 2048; canvas.height = 1024;
  const ctx = canvas.getContext('2d')!;
  const gradient = ctx.createLinearGradient(0, 0, 0, canvas.height);
  if (mode === 'sky') {
    gradient.addColorStop(0, '#175bb7'); gradient.addColorStop(0.48, '#8ecdf0');
    gradient.addColorStop(0.6, '#dcecf2'); gradient.addColorStop(1, '#91bad6');
  } else {
    gradient.addColorStop(0, '#020614'); gradient.addColorStop(0.55, '#0d1734'); gradient.addColorStop(1, '#030813');
  }
  ctx.fillStyle = gradient; ctx.fillRect(0, 0, canvas.width, canvas.height);
  if (mode === 'stars') {
    let seed = 4187;
    const random = () => { seed = (Math.imul(seed, 1664525) + 1013904223) >>> 0; return seed / 4294967296; };
    for (let i = 0; i < 1500; i++) {
      const x = random() * canvas.width, y = random() * canvas.height, radius = 0.4 + random() * 1.4;
      ctx.fillStyle = `rgba(230,240,255,${0.35 + random() * 0.65})`;
      ctx.beginPath(); ctx.arc(x, y, radius, 0, Math.PI * 2); ctx.fill();
    }
  }
  const texture = new CanvasTexture(canvas); texture.mapping = EquirectangularReflectionMapping; texture.colorSpace = SRGBColorSpace;
  return texture;
}
