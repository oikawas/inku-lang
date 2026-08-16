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
 * A count of bytes, as the canvas strip and the provenance drawer both say it.
 *
 * One function for the two so the number above the drawing and the number
 * inside the drawer cannot drift apart -- they are the same quantity, measured
 * once. Below a kilobyte the bytes are shown as they are: rounding 300 bytes to
 * `0.3 KB` says less than `300 B` does.
 */
export function formatByteSize(bytes: number | null | undefined): string {
	if (bytes == null) return '-';
	if (bytes < 1024) return `${groupDigits(bytes)} B`;
	return `${groupDigits(bytes / 1024, 1)} KB`;
}
