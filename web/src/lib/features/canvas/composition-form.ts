import { formDescription, formName, lawFamily, lawName, lawSummary } from '../composition-record/composition-names.ts';

export const COMPOSITION_FORMS = ['one_corner', 'all_over', 'bands', 'dividing_line', 'grid', 'flock_and_stray', 'unequal_triangle'] as const;
export type CompositionForm = typeof COMPOSITION_FORMS[number];

/** The laws an author can name as the main law: every law but B21 (step 2, 2026-11-13), in the names table's order. */
export const MAIN_LAWS = ['B1', 'B2', 'B3', 'B4', 'B5', 'B6', 'B7', 'B8', 'B9', 'B10', 'B12', 'B15', 'C1', 'C2', 'C3', 'C4', 'C5', 'C6'] as const;
export type MainLaw = typeof MAIN_LAWS[number];

/** What the refinement "Change the composition and laws" changes. A main-law
 *  change keeps the parent's form when the parent has one. */
export type CompositionChange =
	| { kind: 'form'; form: CompositionForm }
	| { kind: 'main_law'; mainLaw: MainLaw; form: CompositionForm | null };

/** The forms with their short names and one-line descriptions, from the composition names table (2026-11-13). */
export function compositionFormOptions(isJapanese: boolean): { id: CompositionForm; name: string; description: string }[] {
	return COMPOSITION_FORMS.map((id) => ({ id, name: formName(id, isJapanese), description: formDescription(id, isJapanese) }));
}

export function isCompositionForm(value: unknown): value is CompositionForm {
	return COMPOSITION_FORMS.includes(value as CompositionForm);
}

export function isMainLaw(value: unknown): value is MainLaw {
	return MAIN_LAWS.includes(value as MainLaw);
}

/** The main laws grouped by family (proportion, balance, rhythm, gradation, card), each law with its name and summary. */
export function mainLawFamilies(isJapanese: boolean): { family: string; laws: { code: MainLaw; name: string; summary: string }[] }[] {
	const families: { family: string; laws: { code: MainLaw; name: string; summary: string }[] }[] = [];
	for (const code of MAIN_LAWS) {
		const family = lawFamily(code, isJapanese);
		let group = families.find((entry) => entry.family === family);
		if (!group) families.push(group = { family, laws: [] });
		group.laws.push({ code, name: lawName(code, isJapanese), summary: lawSummary(code, isJapanese) });
	}
	return families;
}

/** The run options and the derivation metadata a change sends. The Server
 *  builds the saved metadata itself; this is the option's own. */
export function compositionChangeOptions(change: CompositionChange, parent: { form: string | null; mainLaw: string | null }): {
	options: { composition_form?: CompositionForm; composition_main_law?: MainLaw };
	metadata: Record<string, string | null>;
} {
	if (change.kind === 'form') {
		return { options: { composition_form: change.form }, metadata: { form_from: parent.form, form_to: change.form } };
	}
	return {
		options: { ...(change.form ? { composition_form: change.form } : {}), composition_main_law: change.mainLaw },
		metadata: { main_law_from: parent.mainLaw, main_law_to: change.mainLaw, form: change.form },
	};
}
