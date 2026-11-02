export const COMPOSITION_FORMS = ['one_corner', 'all_over', 'bands', 'dividing_line', 'grid', 'flock_and_stray', 'unequal_triangle'] as const;
export type CompositionForm = typeof COMPOSITION_FORMS[number];

export function compositionFormOptions(isJapanese: boolean): { id: CompositionForm; name: string; description: string }[] {
	const names = isJapanese
		? ['一角', '全面', '帯', '分ける線', '格子', '群れと逸れ', '不等辺の三角']
		: ['One corner', 'All over', 'Bands', 'Dividing line', 'Grid', 'Flock and stray', 'Unequal triangle'];
	const descriptions = isJapanese
		? ['主を片隅や片側に寄せて広く空ける', '全面に均して中心を消す', '横の帯を重ねる', '場を分ける線', '格子', '群れと一つの逸脱', '主・従・添えの不等辺の三角']
		: ['Push the focal thing to one side and leave wide space', 'Spread evenly and erase the center', 'Stack horizontal bands', 'Divide the field with a line', 'Grid', 'A flock and one that strays', 'An unequal triangle of focal, secondary and accent'];
	return COMPOSITION_FORMS.map((id, index) => ({ id, name: names[index], description: descriptions[index] }));
}
