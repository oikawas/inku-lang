// How heavy one drawing is: bytes, objects, points.
//
// This file is one half of a pair. The other half is `measure()` in
// no-git-sync/scripts/svg_weight.py, which reports how the same three
// quantities have moved across engine versions and across the saved works. If
// the number on screen and the number in that report are counted by different
// definitions, neither of them can be used, so the two are kept 1:1 -- change
// one and change the other in the same commit.
//
// The three are never merged into one. At render engine 33 the two largest
// cases in the reference corpus were 224,749 B / 158 objects and 222,230 B /
// 680 objects: the same 220 KB made of four times the number of shapes. Bytes
// and objects correlate at r = 0.923, which is too high to tell apart by eye
// and too low to stand in for one another.

// A tag opens with a letter; `</rect>` never matches, because `/` is not one.
const ELEMENT_RE = /<([a-zA-Z][a-zA-Z0-9_-]*)/g;
const POINTS_RE = /points="([^"]*)"/g;
// \b keeps `id="…"` out -- there is no word boundary between `i` and `d`.
const PATH_D_RE = /\bd="([^"]*)"/g;
const NUMBER_RE = /-?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?/g;

// Structure, not ink. These five carry no mark of their own, so counting them
// would report the shape of the file instead of the shape of the drawing.
const NOT_AN_OBJECT = new Set(['svg', 'title', 'desc', 'metadata', 'defs']);

export type SvgWeight = {
	/** UTF-8 byte length of the SVG text. */
	bytes: number;
	/** Drawn elements, excluding the five structural tags. */
	objects: number;
	/** Points on those elements: `points` tokens plus half the numbers in `d`. */
	points: number;
};

/**
 * Measure one drawing from its SVG source.
 *
 * The input is the SVG string, never the DOM. `querySelectorAll('*')` counts a
 * different quantity: it excludes nothing, it descends into `<defs>`, and the
 * page can be showing several copies of the same drawing side by side.
 */
export function measureSvgWeight(svg: string): SvgWeight {
	let objects = 0;
	for (const match of svg.matchAll(ELEMENT_RE)) {
		if (!NOT_AN_OBJECT.has(match[1])) objects += 1;
	}

	let points = 0;
	for (const match of svg.matchAll(POINTS_RE)) {
		// Whitespace-separated tokens, so `10,20 30,40` is two points. Empty
		// tokens are dropped, the way Python's str.split() with no argument does.
		points += match[1].split(/\s+/).filter((token) => token.length > 0).length;
	}
	for (const match of svg.matchAll(PATH_D_RE)) {
		// A path says its numbers in pairs, so the number of points is half of
		// them. Truncating is deliberate: an odd count is a malformed path, and
		// rounding it up would invent a point that was never drawn.
		points += Math.floor((match[1].match(NUMBER_RE)?.length ?? 0) / 2);
	}

	return { bytes: new TextEncoder().encode(svg).length, objects, points };
}
