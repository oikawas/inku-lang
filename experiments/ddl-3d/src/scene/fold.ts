/** How thin the solids become at the front, so they overlap in drawing order
 * as in 2D. A folded solid keeps at most a quarter of the smallest gap between
 * two layers on each side, and never more than 0.2% of its thickness. */

export const FOLDED = 0.002;
const SMALLEST = 1e-4;

/** The smallest gap between two different layer depths. */
export function smallestLayerGap(layerZ: Iterable<number>): number {
  const depths = [...new Set(layerZ)].sort((a, b) => a - b);
  let gap = Infinity;
  for (let i = 1; i < depths.length; i++) gap = Math.min(gap, depths[i] - depths[i - 1]);
  return gap;
}

/** The share of its thickness a solid keeps at the front. `thickness` is the
 * solid's own depth along z; `gap` is the smallest layer gap, both as drawn. */
export function foldedShare(thickness: number, gap: number): number {
  if (!(thickness > 0)) return FOLDED;
  return Math.max(SMALLEST, Math.min(FOLDED, gap / 4 / thickness));
}
