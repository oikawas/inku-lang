import { formDescription, formName } from '../composition-record/composition-names.ts';

export const COMPOSITION_FORMS = ['one_corner', 'all_over', 'bands', 'dividing_line', 'grid', 'flock_and_stray', 'unequal_triangle'] as const;
export type CompositionForm = typeof COMPOSITION_FORMS[number];

/** The forms with their short names and one-line descriptions, from the composition names table (2026-11-13). */
export function compositionFormOptions(isJapanese: boolean): { id: CompositionForm; name: string; description: string }[] {
	return COMPOSITION_FORMS.map((id) => ({ id, name: formName(id, isJapanese), description: formDescription(id, isJapanese) }));
}
