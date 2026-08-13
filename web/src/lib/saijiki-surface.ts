// The saijiki previews for the surface words (おもて / surfaces).
//
// The other ten categories say what to place; this one says how a face is --
// saijiki.py marks it as carrying no closure marker for exactly that reason.
// So every drawing here is the same rectangle with a different interior. The
// contour never changes, and hovering across the row shows only the face
// changing, which is what the category means.
//
// What each word does is the server's, not this file's: the mapping from word
// to `instruction.surface` is fixed in composer.py, and the marks are drawn by
// renderer.py's `_render_surface_vectors`. The drawings below follow those two
// -- the hatch angle, the two wash sweeps, the three aquatint steps and the
// density figures behind 濃い / 薄い are all read from there, not invented.

/** One preview: the copy in both UI languages, and the drawing they share. */
export type PreviewEntry = {
	effect: string;
	example: string;
	effectEn: string;
	exampleEn: string;
	svg: string;
};

/** The preview frame every saijiki drawing sits in: paper, then the marks. */
export const shapeSvg = (shape: string) =>
	`<svg viewBox="0 0 180 92" aria-hidden="true"><rect width="180" height="92" rx="6" fill="#fffdf8"/>${shape}</svg>`;

/** The one contour all eleven surface drawings share. */
export const SURFACE_BOX = 'x="50" y="20" width="80" height="52" rx="2"';

/**
 * One surface drawing: the shared contour, an interior clipped to it, and
 * anything belonging outside the contour -- bleeding is an edge and not a
 * face, so it is the one word that draws there.
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
 * The drawing for a relative word. 濃い and 薄い are not textures: they move
 * the density and the opacity of a texture that is already there. So each half
 * of the box holds the same stipple, the left at the default (density 0.35)
 * and the right at what the word asks for, and the drawing shows the change
 * rather than a texture of its own. The counts follow the renderer's own
 * 22 + density * 120, taken down to a half box.
 */
export const surfaceRelative = (count: number, opacity: number): string =>
	surfaceDabs(21, 2.1, 0.28, 4.5, 51, 89) +
	surfaceDabs(count, 2.1, opacity, 8.5, 91, 129) +
	'<path d="M90 20 V72" stroke="#d7d1c4" stroke-width="1.5"/>';

/** Keyed by the Japanese surface, the way the rest of the preview table is. */
export const SURFACE_PREVIEWS: Record<string, PreviewEntry> = {
	空: {
		effect: '面に何も置かない。輪郭だけが残る既定の状態。',
		example: '空の四角を置く',
		effectEn: 'Leaves the face untouched. The default, where only the contour remains.',
		exampleEn: 'Place an empty square',
		svg: surfaceSvg('')
	},
	塗り: {
		effect: '質感ではなく、面を一様に塗りつぶす。',
		example: '中を塗った四角を置く',
		effectEn: 'Not a texture: fills the face evenly.',
		exampleEn: 'Place a filled square',
		svg: surfaceSvg(`<rect ${SURFACE_BOX} fill="#2b2b2b"/>`)
	},
	薄墨: {
		effect: '同じ面を角度をわずかに変えて二度掃く。重なった所だけが濃くなる。',
		example: '薄墨で四角を塗る',
		effectEn:
			'Sweeps the same face twice at slightly different angles; only the overlaps darken.',
		exampleEn: 'Wash a square with pale ink',
		svg: surfaceSvg(
			'<defs><filter id="surface-wash"><feGaussianBlur stdDeviation="2.4"/></filter></defs>' +
				'<g filter="url(#surface-wash)" stroke="#2b2b2b" stroke-width="15" stroke-linecap="round">' +
				'<g><path d="M44 26 H136" opacity="0.2"/><path d="M44 39 H136" opacity="0.26"/><path d="M44 52 H136" opacity="0.18"/><path d="M44 65 H136" opacity="0.24"/></g>' +
				'<g transform="rotate(6 90 46)"><path d="M44 22 H136" opacity="0.22"/><path d="M44 35 H136" opacity="0.17"/><path d="M44 48 H136" opacity="0.25"/><path d="M44 61 H136" opacity="0.19"/><path d="M44 74 H136" opacity="0.22"/></g>' +
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
	点: {
		effect: '点を面に撒いて濃淡を作る。',
		example: '点で面を埋める',
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
	にじみ: {
		effect: '輪郭の外へ墨が染み出す。面の中ではなく縁の話。',
		example: '縁がにじむ四角を置く',
		effectEn: 'Ink seeps outward past the contour. It is about the edge, not the interior.',
		exampleEn: 'Place a square with a bleeding edge',
		svg: surfaceSvg(
			'',
			'<defs><filter id="surface-bleed" x="-25%" y="-45%" width="150%" height="190%"><feGaussianBlur stdDeviation="3"/></filter></defs>' +
				'<g fill="none" stroke="#2b2b2b" filter="url(#surface-bleed)">' +
				'<path d="M43 16 C62 9 104 8 135 16 C142 31 141 62 133 76 C108 85 66 87 50 78 C42 61 40 31 43 16 Z" stroke-width="5" opacity="0.13"/>' +
				'<path d="M47 18 C64 13 102 12 132 19 C138 32 137 60 131 73 C107 80 69 81 52 74 C46 60 44 31 47 18 Z" stroke-width="8" opacity="0.3"/>' +
				'</g>'
		)
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
	},
	濃い: {
		effect: '他の面の語に添えて、その質感を濃くする。単独の質感ではない。',
		example: '濃い薄墨で塗る',
		effectEn:
			'Attaches to another surface word and makes that texture denser. Not a texture of its own.',
		exampleEn: 'Wash densely with pale ink',
		svg: surfaceSvg(surfaceRelative(31, 0.5))
	},
	薄い: {
		effect: '他の面の語に添えて、その質感を淡くする。単独の質感ではない。',
		example: '薄い平行線で埋める',
		effectEn:
			'Attaches to another surface word and makes that texture fainter. Not a texture of its own.',
		exampleEn: 'Fill with a faint hatch',
		svg: surfaceSvg(surfaceRelative(15, 0.15))
	}
};
