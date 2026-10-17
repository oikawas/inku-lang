import type { InitialView } from '../input/protocol';

/** Match the host's canvas pixels, independent of layer Z and mesh bounds. */
export function frontView(canvas: [number, number], width: number, height: number, initial?: InitialView) {
  const pixelsPerUnit = initial ? initial.pixelHeight / canvas[1]
    : Math.max(1, Math.min(width / canvas[0], height / canvas[1]) * 0.9);
  return {
    height: height / pixelsPerUnit,
    target: [-(initial?.panX ?? 0) / pixelsPerUnit, (initial?.panY ?? 0) / pixelsPerUnit, 0] as [number, number, number],
    referenceHeight: height / pixelsPerUnit * (initial?.zoom ?? 1),
  };
}
