// Derivation kinds (the operation that made a work from its parent). Single
// source for the labels, shared by the lineage panel and the provenance drawer.
// A work with no kind recorded is the origin of its lineage.
import { formName, lawName, placeName } from './features/composition-record/composition-names.ts';

export type DerivationKind =
	| 'touch_change'
	| 'layout_change'
	| 'catalog_change'
	| 'color_arrangement_change'
	| 'ground_change'
	| 'tool_change'
	| 'reinterpretation'
	| 'model_comparison'
	| 'language_comparison'
	| 'ddl_edit'
	| 'description_edit'
	| 'replay'
	| 'canvas_aspect_change'
	| 'composition_form_change'
	// The saved Score fitted into another paper (DDL 26, 2026-10-23).
	| 'canvas_fit'
	// Sketch from life (Stage 0.5, v2.10): redrawn at a different grain.
	| 'sketch_grain_change';

const JA: Record<string, string> = {
	touch_change: 'タッチ',
	layout_change: '配置',
	catalog_change: '色',
	color_arrangement_change: '配色',
	ground_change: '支持体',
	tool_change: 'てざわり',
	reinterpretation: '解釈',
	model_comparison: 'モデル',
	language_comparison: '言語',
	ddl_edit: 'DDL編集',
	description_edit: '記述編集',
	replay: '再描画',
	canvas_aspect_change: 'キャンバス変更',
	composition_form_change: '構図と法則',
	canvas_fit: 'はめ込み',
	variation: '変奏（旧）',
	sketch_grain_change: '写生の有無',
	// The AI refinement's laws move and chunk move; the Server's run writes them, no screen sends them.
	laws_change: '法則',
	chunk_move: 'まとまりの手'
};

const EN: Record<string, string> = {
	touch_change: 'Touch',
	layout_change: 'Layout',
	catalog_change: 'Color',
	color_arrangement_change: 'Color arrangement',
	ground_change: 'Ground',
	tool_change: 'Touches',
	reinterpretation: 'Reading',
	model_comparison: 'Model',
	language_comparison: 'Language',
	ddl_edit: 'DDL edit',
	description_edit: 'Description edit',
	replay: 'Replay',
	canvas_aspect_change: 'Canvas change',
	composition_form_change: 'Composition and laws',
	canvas_fit: 'Fit',
	variation: 'Variation (retired)',
	sketch_grain_change: 'Sketch from life',
	laws_change: 'Laws',
	chunk_move: 'Chunk move'
};

export function derivationKindLabel(kind: string | null | undefined, isJapanese: boolean): string {
	return (isJapanese ? JA : EN)[kind ?? ''] ?? (kind || (isJapanese ? '起点' : 'Origin'));
}

/** What an edge's metadata adds to its kind's label, if anything (2026-11-13).
 *  A form change that recorded both forms reads "画の型: 分ける線 → 帯", and a
 *  main-law change that recorded both laws reads "主の法則: 黄金分割 → 漸進"
 *  (step 2); a form or law a newer core named and this table does not have
 *  reads as its key. */
export function derivationDetail(kind: string | null | undefined, metadata: unknown, isJapanese: boolean): string | null {
	if (kind === 'layout_change' && metadata && typeof metadata === 'object') {
		// One thing moved to a place (step 3): "磯の岩肌: 黄金分割・右下の交点 → 中心".
		const place = (metadata as { place?: unknown }).place;
		if (!place || typeof place !== 'object') return null;
		const { title, at_from: from, at } = place as { title?: unknown; at_from?: unknown; at?: unknown };
		if (typeof title !== 'string' || !title || typeof at !== 'string' || !at) return null;
		const before = typeof from === 'string' && from ? placeName(from, isJapanese) : (isJapanese ? '置き場の外' : 'off the places');
		return `${title}: ${before} → ${placeName(at, isJapanese)}`;
	}
	if (kind !== 'composition_form_change' || !metadata || typeof metadata !== 'object') return null;
	const { main_law_from: lawFrom, main_law_to: lawTo } = metadata as { main_law_from?: unknown; main_law_to?: unknown };
	if (typeof lawTo === 'string' && lawTo) {
		if (typeof lawFrom !== 'string' || !lawFrom) return null;
		return `${isJapanese ? '主の法則: ' : 'Main law: '}${lawName(lawFrom, isJapanese)} → ${lawName(lawTo, isJapanese)}`;
	}
	const { form_from: from, form_to: to } = metadata as { form_from?: unknown; form_to?: unknown };
	if (typeof from !== 'string' || !from || typeof to !== 'string' || !to) return null;
	const term = isJapanese ? '画の型: ' : 'Form: ';
	return `${term}${formName(from, isJapanese)} → ${formName(to, isJapanese)}`;
}

/** Which edge a redraw from the describe tab writes.
 *
 *  One edge, one cause (SPEC section 7): a changed description is a description
 *  edit even if the grain moved with it, and a redraw that changed nothing at
 *  all stays a replay. The sketch-from-life (Stage 0.5) grain gets its own kind only when
 *  it is the thing that differs from the parent -- the same shape
 *  description_edit has always had.
 *
 *  Lives here rather than inline in the page so the rule has one home and can
 *  be read on its own.
 */
export function submitDerivationKind(input: {
	hasParent: boolean;
	canvasAspectChanged: boolean;
	textChanged: boolean;
	grainChanged: boolean;
}): DerivationKind | null {
	if (input.canvasAspectChanged) return 'canvas_aspect_change';
	if (!input.hasParent) return null;
	if (input.textChanged) return 'description_edit';
	if (input.grainChanged) return 'sketch_grain_change';
	return 'replay';
}
