// How a description is drawn (2026-10-25, SPEC 12.6.7). Single source for the
// values and labels.
//
// 'stages' is the drawing as it was: Stage 1, the composition reading, the laws
// and the colors. 'read_and_draw' reads the description from the speaker's eye,
// writes what that eye sees as DDL, and corrects it once beside its drawing.
// Chosen per draw, like the sketch, and never kept as a setting: a work opened
// from the history sets it to the way that work was drawn.
//
// The sketch keeps its two choices on both routes. On read_and_draw, 'on' is
// the reading and 'off' writes from the description alone; choosing
// read_and_draw starts the sketch on (the author's answer, 2026-10-25), and the
// current stages keep their default, off.
import type { SketchMode } from './sketch';

export type DrawRoute = 'stages' | 'read_and_draw';
export const DRAW_ROUTES: DrawRoute[] = ['stages', 'read_and_draw'];
export const DEFAULT_DRAW_ROUTE: DrawRoute = 'stages';

export function drawRouteLabel(route: DrawRoute, isJapanese: boolean): string {
	if (route === 'read_and_draw') return isJapanese ? '読んで描く' : 'Read and draw';
	return isJapanese ? '今の流れ' : 'Current stages';
}

export function drawRouteHint(route: DrawRoute, isJapanese: boolean): string {
	if (route === 'read_and_draw') {
		return isJapanese
			? '記述を語り手の目から読み、見えた景を指示書に書いて、描いた画を見て一度直す'
			: "Read the description from the speaker's eye, write what that eye sees, and correct it once beside its drawing";
	}
	return isJapanese
		? '解釈・構図の読み・法則・配色の段を通して描く'
		: 'Draw through interpretation, the composition reading, the laws and the colors';
}

/** The sketch a route starts from when the author chooses it. */
export function sketchModeForRoute(route: DrawRoute, current: SketchMode): SketchMode {
	return route === 'read_and_draw' ? 'on' : current;
}

export function normalizeDrawRoute(value: unknown): DrawRoute | null {
	return value === 'stages' || value === 'read_and_draw' ? value : null;
}

/** The route a work or a run was drawn by: a read-and-draw work keeps its record. */
export function drawRouteOf(work: { route?: unknown; description_ddl?: unknown } | null | undefined): DrawRoute {
	const named = normalizeDrawRoute(work?.route);
	if (named) return named;
	return work?.description_ddl && typeof work.description_ddl === 'object' ? 'read_and_draw' : DEFAULT_DRAW_ROUTE;
}

/** How the work on screen was drawn, as the strip above the canvas names it:
 *  a work written from a picture went through neither route. */
export function workRouteLabel(
	work: { route?: unknown; description_ddl?: unknown; image_ddl?: unknown } | null | undefined,
	isJapanese: boolean
): string {
	if (work?.image_ddl && typeof work.image_ddl === 'object') return isJapanese ? '画像から書く' : 'Written from a picture';
	return drawRouteLabel(drawRouteOf(work), isJapanese);
}

// The composition and laws (2026-10-26, SPEC 12.6.7): a switch inside read and
// draw. 'on' decides a composition and laws from the description (and its
// reading) before the DDL is written; 'off', the default, is read and draw as
// it was. Chosen per draw like the route and never kept as a setting; a work
// opened from the history sets it to the way that work was drawn.
export type CompositionMode = 'off' | 'on';
export const COMPOSITION_MODES: CompositionMode[] = ['off', 'on'];
export const DEFAULT_COMPOSITION_MODE: CompositionMode = 'off';

export function compositionModeLabel(mode: CompositionMode, isJapanese: boolean): string {
	if (mode === 'on') return isJapanese ? 'あり' : 'On';
	return isJapanese ? 'なし' : 'Off';
}

export function compositionModeHint(mode: CompositionMode, isJapanese: boolean): string {
	if (mode === 'on') {
		return isJapanese
			? '記述から構図と法則を先に決め、それに沿って指示書を書き、測って合わせ、最後に配色を選ぶ'
			: 'Decide a composition and laws from the description first, write the DDL toward them and fit it, then choose its colors';
	}
	return isJapanese ? '記述をそのまま画に置き換える（今の読んで描く）' : 'Turn the description straight into the picture (read and draw as before)';
}

export function normalizeCompositionMode(value: unknown): CompositionMode | null {
	return value === 'off' || value === 'on' ? value : null;
}

/** Whether a work was drawn with the composition and laws: its record says so,
 *  a fallback included (it was asked for and could not be used). */
export function compositionModeOf(work: { description_ddl?: unknown } | null | undefined): CompositionMode {
	const record = work?.description_ddl;
	return record && typeof record === 'object' && (record as DescriptionDdlRecord).composition ? 'on' : DEFAULT_COMPOSITION_MODE;
}

/** The run option the switch adds: only read and draw sends it. */
export function compositionOption(route: DrawRoute, mode: CompositionMode): { composition?: CompositionMode } {
	return route === 'read_and_draw' ? { composition: mode } : {};
}

/** The composition and laws as the core records them (SPEC 12.6.7). */
export type CompositionRecord = {
	state?: 'pending' | 'used' | 'fallback';
	fallback?: string | null;
	answer?: {
		thesis?: string;
		form?: string;
		things?: { thing?: number; what?: string; role?: string; kind?: string; quote?: string }[];
		main_law?: string;
		laws?: Record<string, unknown>;
		reason?: string;
	} | null;
	targets?: string[];
	rounds?: { prompt_id?: string; prompt_digest?: string; asked_again?: boolean; problems?: { where?: string; reason?: string }[] }[];
	measures?: {
		stage?: string;
		fit_kept?: boolean;
		after?: { law?: string; thing?: number | number[] | null; deviation?: number | null; unit?: string; state?: string; detail?: string }[];
		[key: string]: unknown;
	}[];
	cards?: { law?: string; things?: number[]; motif?: string; built?: boolean; reason?: string | null }[];
	things?: number[];
	colors?: CompositionColorsRecord | null;
	[key: string]: unknown;
};

/** The colors chosen after the review, before the commit (2026-10-26). */
export type CompositionColorsRecord = {
	state?: 'used' | 'fallback';
	fallback?: string | null;
	main_law?: string | null;
	laws?: string[];
	ground?: string | null;
	changes?: { line?: number | null; how?: string; before?: string; after?: string[] }[];
};

const COLORS_CHANGE_LABELS: Record<string, [string, string]> = {
	color_word: ['色の語を書き換えた', 'color word rewritten'],
	printed: ['数つきで印字し直した', 'printed again with numbers'],
	ground: ['背景の文を替えた', 'background sentence changed'],
	ground_added: ['背景の文を足した', 'background sentence added'],
};

export const compositionColorsChangeLabel = (how: unknown, isJapanese: boolean) => labelOf(COLORS_CHANGE_LABELS, how, isJapanese);

export function compositionColorsStateNote(record: CompositionColorsRecord, isJapanese: boolean): string {
	if (record.state === 'used') return isJapanese ? '配色を選び、当てて確定した' : 'Colors were chosen and applied before the commit';
	return isJapanese
		? `配色を当てられず、配色の前の指示書で確定した（${record.fallback ?? ''}）`
		: `No colors could be applied, so the DDL before them was committed (${record.fallback ?? ''})`;
}

/** How many lines the colors wrote, by how, in the order they first appear. */
export function compositionColorsChanges(record: CompositionColorsRecord | null | undefined): [string, number][] {
	const counts = new Map<string, number>();
	for (const change of record?.changes ?? []) counts.set(change.how ?? '', (counts.get(change.how ?? '') ?? 0) + 1);
	return [...counts.entries()];
}

const FORM_LABELS: Record<string, [string, string]> = {
	one_corner: ['一角', 'one corner'],
	all_over: ['全面', 'all over'],
	bands: ['横の帯', 'bands'],
	dividing_line: ['場を分ける線', 'dividing line'],
	grid: ['格子', 'grid'],
	flock_and_stray: ['群れと一つの逸脱', 'flock and a stray'],
	unequal_triangle: ['不等辺の三角', 'unequal triangle'],
};
const ROLE_LABELS: Record<string, [string, string]> = {
	field: ['場', 'field'], focal: ['主', 'focal'], secondary: ['従', 'secondary'],
	scattered: ['散在', 'scattered'], accent: ['添え', 'accent'],
};
const KIND_LABELS: Record<string, [string, string]> = {
	cluster: ['1か所の形', 'cluster'], row: ['列', 'row'], surface: ['面', 'surface'], line: ['線', 'line'],
};
const MEASURE_LABELS: Record<string, [string, string]> = {
	ok: ['合う', 'fits'], off: ['少しずれ', 'a little off'], far: ['大きくずれ', 'far off'],
	fitted: ['合わせた', 'fitted'], clamped: ['範囲の端に合わせた', 'clamped'], off_canvas: ['画の外', 'off the canvas'],
	unmeasurable: ['測れない', 'unmeasurable'], not_measured: ['測っていない', 'not measured'],
};

function labelOf(table: Record<string, [string, string]>, value: unknown, isJapanese: boolean): string {
	const pair = typeof value === 'string' ? table[value] : undefined;
	return pair ? pair[isJapanese ? 0 : 1] : typeof value === 'string' ? value : '';
}

export const compositionFormLabel = (form: unknown, isJapanese: boolean) => labelOf(FORM_LABELS, form, isJapanese);
export const compositionRoleLabel = (role: unknown, isJapanese: boolean) => labelOf(ROLE_LABELS, role, isJapanese);
export const compositionKindLabel = (kind: unknown, isJapanese: boolean) => labelOf(KIND_LABELS, kind, isJapanese);
export const compositionMeasureLabel = (state: unknown, isJapanese: boolean) => labelOf(MEASURE_LABELS, state, isJapanese);

export function compositionStateNote(record: CompositionRecord | null | undefined, isJapanese: boolean): string {
	if (record?.state === 'used') return isJapanese ? '構図と法則を決め、それに沿って書いた' : 'A composition and laws were decided, and the DDL was written toward them';
	if (record?.state === 'fallback') {
		const reason = record.fallback === 'refused'
			? (isJapanese ? '答えが決まりに合わなかった' : 'the answers broke the rules')
			: (record.fallback ?? '');
		return isJapanese
			? `構図と法則を決められず、構図と法則なしで書いた（${reason}）`
			: `No composition and laws could be decided, so it was written without them (${reason})`;
	}
	return isJapanese ? '構図と法則を決めている途中' : 'Deciding the composition and laws';
}

/** The last measure's states, counted, and the pairs that did not fit. A pair
 * the tool does not measure (the hand of B21, drawn by the writer) is counted
 * but did not miss. */
export function compositionMeasureSummary(record: CompositionRecord | null | undefined): {
	counts: [string, number][];
	misses: { law: string; thing: string; state: string }[];
} {
	const last = record?.measures?.at(-1)?.after ?? [];
	const counts = new Map<string, number>();
	const misses: { law: string; thing: string; state: string }[] = [];
	for (const measure of last) {
		const state = measure.state ?? '';
		counts.set(state, (counts.get(state) ?? 0) + 1);
		if (state !== 'ok' && state !== 'fitted' && state !== 'clamped' && state !== 'not_measured') {
			const thing = Array.isArray(measure.thing) ? measure.thing.join('・') : measure.thing == null ? '' : String(measure.thing);
			misses.push({ law: measure.law ?? '', thing, state });
		}
	}
	return { counts: [...counts.entries()], misses };
}

/** The record the core keeps for a read-and-draw run (SPEC 12.6.7). */
export type DescriptionDdlRecord = {
	description?: string;
	source_labels?: string[];
	reading_state?: 'off' | 'pending' | 'read' | 'supplied' | 'fallback';
	reading?: Record<string, unknown> | null;
	reading_text?: string | null;
	/** Items whose quote neither the description nor a label holds. */
	dropped_items?: { kind?: string; quote?: string; image?: string }[];
	/** The viewpoint's quotes emptied for the same reason, by name. */
	dropped_quotes?: Record<string, string>;
	rounds?: DescriptionDdlRound[];
	before_review?: string | null;
	drawing?: Record<string, unknown> | null;
	/** Lines left out because each alone stopped the whole work. */
	dropped?: string[];
	/** The composition and laws, when the run was drawn with them. */
	composition?: CompositionRecord | null;
	[key: string]: unknown;
};

export type DescriptionDdlRound = {
	/** write_description_ddl or review_description_ddl. */
	stage?: string;
	prompt_id?: string;
	prompt_digest?: string;
	asked_again?: boolean;
	problems?: number;
	instructions?: number;
	figures?: { who?: string; what?: string }[];
	[key: string]: unknown;
};

export function readingStateNote(state: unknown, isJapanese: boolean): string {
	if (state === 'read') return isJapanese ? '記述を読み、その読みで書いた' : 'The description was read, and written from the reading';
	if (state === 'supplied') return isJapanese ? '作者が直した読みで書いた' : "Written from the author's edited reading";
	if (state === 'fallback') return isJapanese ? '読みが届かず、記述だけから書いた' : 'The reading did not answer, so it was written from the description alone';
	if (state === 'pending') return isJapanese ? '読んでいる途中' : 'Reading';
	return isJapanese ? '読まずに記述だけから書いた' : 'Written from the description alone, without a reading';
}

/** The lines the anchor check dropped: each item, then each viewpoint quote. */
export function droppedReadingLines(record: DescriptionDdlRecord | null | undefined): string[] {
	const items = (record?.dropped_items ?? []).map((item) =>
		[item.kind, item.quote ? `「${item.quote}」` : null, item.image].filter(Boolean).join(' '));
	const quotes = Object.entries(record?.dropped_quotes ?? {}).map(([name, quote]) => `${name} 「${quote}」`);
	return [...items, ...quotes];
}

/** Who a drawn figure is, as the round records it. */
export function figureWhoLabel(who: unknown, isJapanese: boolean): string {
	if (who === 'speaker') return isJapanese ? '語り手' : 'speaker';
	if (who === 'speaker_part') return isJapanese ? '語り手の体の一部' : "part of the speaker's body";
	if (who === 'addressee') return isJapanese ? '語りかける相手' : 'addressee';
	if (who === 'third') return isJapanese ? 'ほかの人' : 'someone else';
	return typeof who === 'string' ? who : '';
}
