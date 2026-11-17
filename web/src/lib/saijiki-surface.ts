// The saijiki previews for surfaces (おもて), handling (さばき), fineness (きめ)
// and underlayer (したじ).
//
// Surfaces say how a face is; handling says how ink or paint is laid down;
// fineness and underlayer say how a texture is laid (DDL 24). So every drawing
// here is the same rectangle with a different interior. The contour never
// changes, and hovering across the row shows only the face changing, which is
// what the category means.
//
// These explanatory drawings follow SPEC §3.3 and the shared Rust renderer's
// surfaces.rs / marks.rs: two sweeps as films at 0.6, brushmarks bands at 0.5
// each, one or two hatch sets, three aquatint steps, and handling relative to
// the tool's opacity. They are stable
// illustrations, not performances of a Score.

import type { ResolvedInstructionLang } from './instructionLang';

/** One preview: examples in both languages and the drawing they share. */
export type PreviewEntry = {
	example: string;
	exampleEn: string;
	svg: string;
};

/**
 * Select the example in the language used by the instructions.
 *
 * They do not follow the same language. The effect explains the word to the
 * person looking at it, so it is in the UI language. The example is a fragment
 * of DDL -- `太い線を引く` against `a thick line` -- so it is in the language
 * the DDL is in, which need not be the UI language: the DDL editor offers
 * English words to a Japanese UI whenever the DDL itself is English.
 */
export function localizePreview(
	entry: Pick<PreviewEntry, 'example' | 'exampleEn'>,
	langs: { uiLang: ResolvedInstructionLang; wordLang: ResolvedInstructionLang }
): { example: string } {
	return {
		example: langs.wordLang === 'ja' ? entry.example : entry.exampleEn
	};
}

/** The preview frame every saijiki drawing sits in: paper, then the marks. */
export const shapeSvg = (shape: string) =>
	`<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/>${shape}</svg>`;

/** The one contour all surface drawings share. */
export const SURFACE_BOX = 'x="50" y="20" width="80" height="52" rx="2"';

/**
 * One surface drawing: the shared contour, an interior clipped to it, and
 * anything belonging outside the contour.
 */
export const surfaceSvg = (interior: string, outside = '') =>
	shapeSvg(
		`<defs><clipPath id="surface-clip"><rect ${SURFACE_BOX}/></clipPath></defs>` +
			`<g clip-path="url(#surface-clip)">${interior}</g>${outside}` +
			`<rect ${SURFACE_BOX} fill="none" stroke="#2b2b2b" stroke-width="4"/>`
	);

/**
 * Dabs scattered inside the contour. Each one is placed by hashing its own
 * index, the way the renderer scatters marks, so the drawing is identical on
 * every hover instead of moving under the pointer.
 */
export const surfaceDabs = (
	count: number,
	radius: number,
	opacity: number,
	salt: number,
	x0 = 51,
	x1 = 129,
	fill = '#2b2b2b'
): string => {
	let marks = '';
	for (let i = 0; i < count; i += 1) {
		const h = (n: number) => (((Math.sin((i + 1) * n + salt) * 43758.5453) % 1) + 1) % 1;
		const cx = (x0 + h(12.9898) * (x1 - x0)).toFixed(1);
		const cy = (21 + h(78.233) * 50).toFixed(1);
		const r = (radius * (0.6 + h(37.719) * 0.8)).toFixed(2);
		const o = (opacity * (0.5 + h(19.31) * 0.5)).toFixed(2);
		marks += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="${fill}" opacity="${o}"/>`;
	}
	return marks;
};

/**
 * Line sets across the face. The renderer's default direction is 45 degrees,
 * its spacing tightens as the density rises, and a crosshatch is the same set
 * laid down a second time turned by 60-90 degrees.
 */
export const surfaceHatch = (
	angles: number[],
	spacing: number,
	width: number,
	opacity: number
): string =>
	angles
		.map((angle) => {
			let lines = '';
			for (let offset = -70; offset <= 70; offset += spacing) {
				lines += `<path d="M-12 ${46 + offset} H192"/>`;
			}
			return `<g transform="rotate(${angle} 90 46)" fill="none" stroke="#2b2b2b" stroke-width="${width}" opacity="${opacity}">${lines}</g>`;
		})
		.join('');

/**
 * Handling changes the tool's opacity, not the surface's density. Both halves
 * keep the same stipple geometry. The left is temperate pencil (opacity 0.66),
 * the right the selected handling: ×1.35 / ×1 / ×0.55 from marks.rs.
 */
const handlingRelative = (opacity: number): string =>
	surfaceDabs(21, 2.1, 0.66, 4.5, 51, 89) +
	surfaceDabs(21, 2.1, opacity, 4.5, 91, 129) +
	'<path d="M90 20 V72" stroke="#d7d1c4" stroke-width="1.5"/>';

/** Keyed by the Japanese surface, the way the rest of the preview table is. */
export const SURFACE_PREVIEWS: Record<string, PreviewEntry> = {
	空: {
		example: '空の四角を置く',
		exampleEn: 'Place an empty square',
		svg: surfaceSvg('')
	},
	塗り: {
		example: '塗りの四角を置く',
		exampleEn: 'Place a flat square',
		svg: surfaceSvg(`<rect ${SURFACE_BOX} fill="#2b2b2b"/>`)
	},
	刷き: {
		example: '刷きの四角を置く',
		exampleEn: 'Place a sweep square',
		svg: surfaceSvg(
			'<defs><filter id="surface-sweep"><feGaussianBlur stdDeviation="2.4"/></filter></defs>' +
				'<g filter="url(#surface-sweep)" stroke="#2b2b2b" stroke-width="15" stroke-linecap="round">' +
				'<g opacity="0.6"><path d="M44 26 H136"/><path d="M44 39 H136"/><path d="M44 52 H136"/><path d="M44 65 H136"/></g>' +
				'<g opacity="0.6" transform="rotate(6 90 46)"><path d="M44 22 H136"/><path d="M44 35 H136"/><path d="M44 48 H136"/><path d="M44 61 H136"/><path d="M44 74 H136"/></g>' +
				'</g>'
		)
	},
	刷毛目: {
		example: '刷毛目の四角を置く',
		exampleEn: 'Place a brushmarks square',
		svg: surfaceSvg(
			'<g stroke="#2b2b2b" stroke-linecap="round">' +
				'<g><path stroke-width="13" stroke-opacity="0.5" d="M44 24 H136"/><path stroke-width="11" stroke-opacity="0.5" d="M44 33 H136"/><path stroke-width="14" stroke-opacity="0.5" d="M44 42 H136"/><path stroke-width="12" stroke-opacity="0.5" d="M44 51 H136"/><path stroke-width="13" stroke-opacity="0.5" d="M44 60 H136"/><path stroke-width="11" stroke-opacity="0.5" d="M44 69 H136"/></g>' +
				'<g transform="rotate(6 90 46)"><path stroke-width="12" stroke-opacity="0.5" d="M44 20 H136"/><path stroke-width="14" stroke-opacity="0.5" d="M44 29 H136"/><path stroke-width="11" stroke-opacity="0.5" d="M44 38 H136"/><path stroke-width="13" stroke-opacity="0.5" d="M44 47 H136"/><path stroke-width="12" stroke-opacity="0.5" d="M44 56 H136"/><path stroke-width="14" stroke-opacity="0.5" d="M44 65 H136"/><path stroke-width="11" stroke-opacity="0.5" d="M44 74 H136"/></g>' +
				'</g>'
		)
	},
	粒: {
		example: '粒の四角を置く',
		exampleEn: 'Place a grain square',
		svg: surfaceSvg(surfaceDabs(78, 1.3, 0.5, 1.7))
	},
	点描: {
		example: '点描の円を置く',
		exampleEn: 'Place a stipple square',
		svg: surfaceSvg(surfaceDabs(34, 2.6, 0.62, 5.3))
	},
	平行線: {
		example: '平行線の四角を置く',
		exampleEn: 'Place a hatch square',
		svg: surfaceSvg(surfaceHatch([45], 8, 2, 0.62))
	},
	交差線: {
		example: '交差線の四角を置く',
		exampleEn: 'Place a crosshatch square',
		svg: surfaceSvg(surfaceHatch([45, 115], 9, 2, 0.5))
	},
	メゾチント: {
		example: 'メゾチントの四角を置く',
		exampleEn: 'Place a mezzotint square',
		svg: surfaceSvg(
			surfaceDabs(26, 1.5, 0.28, 2.3, 51, 76) +
				surfaceDabs(26, 1.5, 0.56, 6.1, 77, 103) +
				surfaceDabs(26, 1.5, 0.84, 9.7, 104, 129)
		)
	}
};

/** Handling applies to lines, arcs, textured surfaces and flat fills. */
export const HANDLING_PREVIEWS: Record<string, PreviewEntry> = {
	濃い: {
		example: '鉛筆の濃い点描の四角を置く',
		exampleEn: 'Place a dense stipple pencil square',
		svg: surfaceSvg(handlingRelative(0.66 * 1.35))
	},
	程よい: {
		example: '鉛筆の程よい点描の四角を置く',
		exampleEn: 'Place a moderate stipple pencil square',
		svg: surfaceSvg(handlingRelative(0.66))
	},
	薄い: {
		example: '鉛筆の薄い点描の四角を置く',
		exampleEn: 'Place a faint stipple pencil square',
		svg: surfaceSvg(handlingRelative(0.66 * 0.55))
	}
};

/**
 * Fineness and underlayer (DDL 24) lay a named texture of a closed shape. As
 * for handling, the left half is the default stipple and the right half the
 * chosen word, at render engine 89's factors: 細かい halves a dot and lays four
 * times as many (the same cover), 粗い doubles it and lays a quarter, 密な lays
 * four times as many of the same dots and 疎な a quarter, and 下塗り paints the
 * tool's colour under the dots and lays them 45% toward white, twice as strong
 * (up to the 0.75 cap).
 */
const textureRelative = (right: string): string =>
	surfaceDabs(21, 2.1, 0.66, 4.5, 51, 89) +
	right +
	'<path d="M90 20 V72" stroke="#d7d1c4" stroke-width="1.5"/>';

/** Fineness changes a texture's units: their size, or how many lie in it. */
export const FINENESS_PREVIEWS: Record<string, PreviewEntry> = {
	細かい: {
		example: 'ペンの細かい点描の四角を置く',
		exampleEn: 'Place a pen fine-grained stipple square',
		svg: surfaceSvg(textureRelative(surfaceDabs(84, 2.1 * 0.5, 0.66, 4.5, 91, 129)))
	},
	粗い: {
		example: 'ペンの粗い点描の四角を置く',
		exampleEn: 'Place a pen coarse-grained stipple square',
		svg: surfaceSvg(textureRelative(surfaceDabs(5, 2.1 * 2, 0.66, 4.5, 91, 129)))
	},
	密な: {
		example: 'ペンの密な点描の四角を置く',
		exampleEn: 'Place a pen packed stipple square',
		svg: surfaceSvg(textureRelative(surfaceDabs(84, 2.1, 0.66, 4.5, 91, 129)))
	},
	疎な: {
		example: 'ペンの疎な点描の四角を置く',
		exampleEn: 'Place a pen sparse stipple square',
		svg: surfaceSvg(textureRelative(surfaceDabs(5, 2.1, 0.66, 4.5, 91, 129)))
	}
};

/** Underlayer paints the tool's colour under a texture. */
export const UNDERLAYER_PREVIEWS: Record<string, PreviewEntry> = {
	下塗り: {
		example: 'ペンの下塗りの点描の四角を置く',
		exampleEn: 'Place a pen underpainted stipple square',
		svg: surfaceSvg(
			textureRelative(
				'<rect x="91" y="20" width="39" height="52" fill="#2b2b2b"/>' +
					surfaceDabs(21, 2.1, 0.75, 4.5, 91, 129, '#8a8a8a')
			)
		)
	}
};
