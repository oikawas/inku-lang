import type { InitialView } from '../input/protocol';

/** Match the host's canvas pixels, independent of layer Z and mesh bounds.
 * The paper is fitted inside the host's box, as the 2D picture is: a box of
 * the picture's own shape gives its pixels exactly, and a host that sends a
 * larger area (the iPhone viewer sent its whole screen, 2026-11-20) no longer
 * blows the paper up to the box's height. */
export function frontView(canvas: [number, number], width: number, height: number, initial?: InitialView) {
  const pixelsPerUnit = initial ? Math.min(initial.pixelWidth / canvas[0], initial.pixelHeight / canvas[1])
    : Math.max(1, Math.min(width / canvas[0], height / canvas[1]) * 0.9);
  return {
    height: height / pixelsPerUnit,
    target: [-(initial?.panX ?? 0) / pixelsPerUnit, (initial?.panY ?? 0) / pixelsPerUnit, 0] as [number, number, number],
    referenceHeight: height / pixelsPerUnit * (initial?.zoom ?? 1),
  };
}
