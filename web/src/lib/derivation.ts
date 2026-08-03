// Derivation kinds (the operation that made a work from its parent). Single
// source for the labels, shared by the lineage panel and the provenance drawer.
// A work with no kind recorded is the origin of its lineage.
export type DerivationKind =
	| 'touch_change'
	| 'layout_change'
	| 'catalog_change'
	| 'reinterpretation'
	| 'model_comparison'
	| 'language_comparison'
	| 'ddl_edit'
	| 'description_edit'
	| 'replay'
	| 'canvas_aspect_change'
	| 'variation'
	// 写生 (Stage 0.5, v2.10): redrawn at a different grain.
	| 'sketch_grain_change';

const JA: Record<string, string> = {
	touch_change: 'タッチ',
	layout_change: '構図',
	catalog_change: '色',
	reinterpretation: '解釈',
	model_comparison: 'モデル',
	language_comparison: '言語',
	ddl_edit: 'DDL編集',
	description_edit: '記述編集',
	replay: '再描画',
	canvas_aspect_change: 'キャンバス変更',
	variation: '変奏',
	sketch_grain_change: '写生の区切り'
};

const EN: Record<string, string> = {
	touch_change: 'Touch',
	layout_change: 'Layout',
	catalog_change: 'Color',
	reinterpretation: 'Reading',
	model_comparison: 'Model',
	language_comparison: 'Language',
	ddl_edit: 'DDL edit',
	description_edit: 'Description edit',
	replay: 'Replay',
	canvas_aspect_change: 'Canvas change',
	variation: 'Variation',
	sketch_grain_change: 'Sketch grain'
};

export function derivationKindLabel(kind: string | null | undefined, isJapanese: boolean): string {
	return (isJapanese ? JA : EN)[kind ?? ''] ?? (kind || (isJapanese ? '起点' : 'Root'));
}

/** Which edge a redraw from the describe tab writes.
 *
 *  One edge, one cause (SPEC section 7): a changed description is a description
 *  edit even if the grain moved with it, and a redraw that changed nothing at
 *  all stays a replay. The 写生 (Stage 0.5) grain fires its own kind only when
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
