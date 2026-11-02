import type { LangPack } from '../../i18n/types.ts';

export const COMPOSITION_FORMS = ['one_corner', 'all_over', 'bands', 'dividing_line', 'grid', 'flock_and_stray', 'unequal_triangle'] as const;
export type CompositionForm = typeof COMPOSITION_FORMS[number];

export function compositionFormOptions(strings: LangPack): { id: CompositionForm; name: string; description: string }[] {
	return COMPOSITION_FORMS.map((id, index) => ({ id, name: strings.compositionFormNames[index], description: strings.compositionFormDescriptions[index] }));
}
