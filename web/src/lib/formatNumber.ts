// How a number is written on screen. Not how it is counted -- the quantities
// themselves come from svgWeight.ts and from the record, and nothing here may
// change one.
//
// The locale is pinned rather than taken from the UI language: the grouping is
// meant to be the same mark in both faces of the app, and a locale-driven
// `toLocaleString()` would put a different separator under some interfaces
// while the same drawing is on screen.
const GROUPING_LOCALE = 'en-US';

/** A number with its thousands separated, at a fixed number of decimals. */
export function groupDigits(value: number, fractionDigits = 0): string {
	return value.toLocaleString(GROUPING_LOCALE, {
		minimumFractionDigits: fractionDigits,
		maximumFractionDigits: fractionDigits
	});
}

/**
 * A detailed count of bytes for the provenance drawer.
 *
 * Below a kilobyte the bytes are shown as they are: rounding 300 bytes to
 * `0.3 KB` says less than `300 B` does. The compact canvas strip deliberately
 * uses formatCanvasCapacity instead.
 */
export function formatByteSize(bytes: number | null | undefined): string {
	if (bytes == null) return '-';
	if (bytes < 1024) return `${groupDigits(bytes)} B`;
	return `${groupDigits(bytes / 1024, 1)} KB`;
}

/** The compact capacity printed above the canvas.
 *
 * It is always whole kilobytes. A positive SVG cannot disappear as `0 KB`, so
 * the rounded value has a floor of one; this also makes 0.4 KB read as 1 KB.
 */
export function formatCanvasCapacity(bytes: number | null | undefined): string {
	if (bytes == null) return '-';
	return `${groupDigits(Math.max(1, Math.round(Math.max(0, bytes) / 1024)))} KB`;
}
