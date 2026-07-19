// 添景水準 (tenkei, v1.97). Single source for the level values and labels.
// Server resolution order is: explicit request value > inherited from the
// lineage parent artwork > 'auto'. Omitting the field means "inherit".
export type TenkeiLevel = 'none' | 'sparse' | 'auto';

export const TENKEI_LEVELS: TenkeiLevel[] = ['none', 'sparse', 'auto'];

export const DEFAULT_TENKEI: TenkeiLevel = 'auto';

export function tenkeiLabel(level: TenkeiLevel, isJapanese: boolean): string {
	if (level === 'none') return isJapanese ? 'なし' : 'None';
	if (level === 'sparse') return isJapanese ? '控えめ' : 'Sparse';
	return isJapanese ? 'おまかせ' : 'Auto';
}

export function tenkeiHint(level: TenkeiLevel, isJapanese: boolean): string {
	if (level === 'none') {
		return isJapanese ? '入力に書かれた要素だけを描く' : 'Draw only what the instruction states';
	}
	if (level === 'sparse') {
		return isJapanese ? '添景は控えめに、主題より小さく薄く' : 'Keep staffage sparse, smaller and lighter than the subject';
	}
	return isJapanese ? '現行のまま（添景をAIに任せる）' : 'Current behaviour (leave staffage to the model)';
}

// Artworks saved before v1.97 have no level recorded; treat them as 'auto'.
export function normalizeTenkei(value: unknown): TenkeiLevel | null {
	return value === 'none' || value === 'sparse' || value === 'auto' ? value : null;
}
