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
	| 'variation';

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
	variation: '変奏'
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
	variation: 'Variation'
};

export function derivationKindLabel(kind: string | null | undefined, isJapanese: boolean): string {
	return (isJapanese ? JA : EN)[kind ?? ''] ?? (kind || (isJapanese ? '起点' : 'Root'));
}
