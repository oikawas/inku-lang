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
