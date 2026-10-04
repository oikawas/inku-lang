// The saijiki previews for surfaces (おもて) and handling (さばき).
//
// Surfaces say how a face is; handling says how ink or paint is laid down.
// So every drawing here is the same rectangle with a different interior. The
// contour never changes, and hovering across the row shows only the face
// changing, which is what the category means.
//
// These explanatory drawings follow SPEC §3.3 and the shared Rust renderer's
// surfaces.rs / marks.rs: two sweeps at 0.5, one or two hatch sets, three
// aquatint steps, and handling relative to the tool's opacity. They are stable
// illustrations, not performances of a Score.

import type { ResolvedInstructionLang } from './instructionLang';

/** One preview: the copy in both languages, and the drawing they share. */
export type PreviewEntry = {
	effect: string;
	example: string;
	effectEn: string;
	exampleEn: string;
	svg: string;
};

/**
 * The two texts of a preview, each in the language its reader needs.
 *
 * They do not follow the same language. The effect explains the word to the
 * person looking at it, so it is in the UI language. The example is a fragment
 * of DDL -- `太い線を引く` against `a thick line` -- so it is in the language
 * the DDL is in, which need not be the UI language: the DDL editor offers
 * English words to a Japanese UI whenever the DDL itself is English.
 */
export function localizePreview(
	entry: Pick<PreviewEntry, 'effect' | 'example' | 'effectEn' | 'exampleEn'>,
	langs: { uiLang: ResolvedInstructionLang; wordLang: ResolvedInstructionLang }
): { effect: string; example: string } {
	return {
		effect: langs.uiLang === 'ja' ? entry.effect : entry.effectEn,
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
	x1 = 129
): string => {
	let marks = '';
	for (let i = 0; i < count; i += 1) {
		const h = (n: number) => (((Math.sin((i + 1) * n + salt) * 43758.5453) % 1) + 1) % 1;
		const cx = (x0 + h(12.9898) * (x1 - x0)).toFixed(1);
		const cy = (21 + h(78.233) * 50).toFixed(1);
		const r = (radius * (0.6 + h(37.719) * 0.8)).toFixed(2);
		const o = (opacity * (0.5 + h(19.31) * 0.5)).toFixed(2);
		marks += `<circle cx="${cx}" cy="${cy}" r="${r}" fill="#2b2b2b" opacity="${o}"/>`;
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
		effect: '面には何も置かず、輪郭を残す。',
		example: '空の四角を置く',
		effectEn: 'Leaves the face untouched, keeping the contour.',
		exampleEn: 'Place an empty square',
		svg: surfaceSvg('')
	},
	塗り: {
		effect: '面を一様に塗りつぶす。',
		example: '塗りの四角を置く',
		effectEn: 'Fills the face evenly.',
		exampleEn: 'Place a flat square',
		svg: surfaceSvg(`<rect ${SURFACE_BOX} fill="#2b2b2b"/>`)
	},
	刷き: {
		effect: '少し角度を変えて面を二度掃く。各掃きは道具の不透明度の半分で、薄いを添えると淡くなる。線や弧では幅広い帯を作る。',
		example: '刷きの四角を置く',
		effectEn:
			'Sweeps the face twice at slightly different angles, each at half the tool opacity. Faint handling makes it paler. On a line or arc it makes a broad band.',
		exampleEn: 'Place a sweep square',
		svg: surfaceSvg(
			'<defs><filter id="surface-sweep"><feGaussianBlur stdDeviation="2.4"/></filter></defs>' +
				'<g filter="url(#surface-sweep)" stroke="#2b2b2b" stroke-width="15" stroke-linecap="round">' +
				'<g opacity="0.5"><path d="M44 26 H136"/><path d="M44 39 H136"/><path d="M44 52 H136"/><path d="M44 65 H136"/></g>' +
				'<g opacity="0.5" transform="rotate(6 90 46)"><path d="M44 22 H136"/><path d="M44 35 H136"/><path d="M44 48 H136"/><path d="M44 61 H136"/><path d="M44 74 H136"/></g>' +
				'</g>'
		)
	},
	粒: {
		effect: '細かい粒を面に撒き、擦れた粗さを出す。',
		example: '粒の立つ面にする',
		effectEn: 'Scatters fine grain across the face for a scuffed roughness.',
		exampleEn: 'A grainy face',
		svg: surfaceSvg(surfaceDabs(78, 1.3, 0.5, 1.7))
	},
	点描: {
		effect: '点を面に撒いて濃淡を作る。',
		example: '点描の円を置く',
		effectEn: 'Scatters dots across the face to build tone.',
		exampleEn: 'Fill the face with stipple',
		svg: surfaceSvg(surfaceDabs(34, 2.6, 0.62, 5.3))
	},
	平行線: {
		effect: '平行な線で面を埋める。密度が上がるほど線の間隔が詰まる。',
		example: '平行線で四角を埋める',
		effectEn: 'Fills the face with parallel lines; the denser it is, the tighter the spacing.',
		exampleEn: 'Fill a square with hatch',
		svg: surfaceSvg(surfaceHatch([45], 8, 2, 0.62))
	},
	交差線: {
		effect: '平行線にもう一組を交差させて重ねる。',
		example: '交差線で四角を埋める',
		effectEn: 'Lays a second set of lines across the first.',
		exampleEn: 'Fill a square with crosshatch',
		svg: surfaceSvg(surfaceHatch([45, 115], 9, 2, 0.5))
	},
	アクアチント: {
		effect: '粒の濃さを段に分ける。既定は三段。',
		example: 'アクアチント三段の四角',
		effectEn: 'Divides the grain into discrete tone steps, three by default.',
		exampleEn: 'A square in three-step aquatint',
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
		effect: '道具の本来の濃さより濃く置く。線・弧・質感の面・塗りに添えられる。図は左が程よい鉛筆の点描、右が濃い点描。',
		example: '鉛筆で濃い点描の四角を置く',
		effectEn:
			'Lays ink or paint more densely relative to the tool, on lines, arcs, textured faces or flat fills. Left: temperate pencil stipple; right: dense stipple.',
		exampleEn: 'Place a dense stipple square with a pencil',
		svg: surfaceSvg(handlingRelative(0.66 * 1.35))
	},
	程よい: {
		effect: '道具の本来の濃さで置く。さばきを省略した痕と同じ。図は左右とも程よい鉛筆の点描。',
		example: '鉛筆で程よい点描の四角を置く',
		effectEn: 'Lays ink or paint at the tool’s own opacity, as when handling is omitted. Both halves show temperate pencil stipple.',
		exampleEn: 'Place a temperate stipple square with a pencil',
		svg: surfaceSvg(handlingRelative(0.66))
	},
	薄い: {
		effect: '道具の本来の濃さより淡く置く。線・弧・質感の面・塗りに添えられる。図は左が程よい鉛筆の点描、右が薄い点描。',
		example: '鉛筆で薄い点描の四角を置く',
		effectEn:
			'Lays ink or paint more faintly relative to the tool, on lines, arcs, textured faces or flat fills. Left: temperate pencil stipple; right: faint stipple.',
		exampleEn: 'Place a faint stipple square with a pencil',
		svg: surfaceSvg(handlingRelative(0.66 * 0.55))
	}
};
