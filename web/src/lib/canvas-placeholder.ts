/**
 * Where the empty-canvas motif sits inside the placeholder frame.
 *
 * The frame follows the chosen canvas proportion, but the motif must not: a
 * circle has to stay a circle and a square a square at every aspect. So the
 * motif is authored in a square of its own and placed in the frame with one
 * uniform scale -- never a separate factor per axis, which is what turned the
 * triangle into a needle at Pillar (1:5).
 *
 * Plain .ts (no runes), so the placement is testable without the compiler --
 * the same split features/color-catalog/render.ts uses.
 */

/** The side of the square the motif is drawn in. */
export const PLACEHOLDER_MOTIF = 1000;

export type MotifPlacement = {
	/** Uniform, so the shapes keep their proportions. */
	scale: number;
	offsetX: number;
	offsetY: number;
};

/**
 * The motif fills the frame's shorter side and is centred on the longer one.
 *
 * Filling the longer side instead would need a second scale factor, which is
 * the distortion this exists to prevent; leaving it at a fixed size would make
 * it shrink away on a large canvas.
 */
export function placeholderMotifPlacement(width: number, height: number): MotifPlacement {
	const side = Math.max(0, Math.min(width, height));
	return {
		scale: side / PLACEHOLDER_MOTIF,
		offsetX: (width - side) / 2,
		offsetY: (height - side) / 2
	};
}

/** The same placement as an SVG transform, for the one element that carries it. */
export function placeholderMotifTransform(width: number, height: number): string {
	const { scale, offsetX, offsetY } = placeholderMotifPlacement(width, height);
	return `translate(${offsetX} ${offsetY}) scale(${scale})`;
}
