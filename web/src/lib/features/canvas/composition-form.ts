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
	| { kind: 'main_law'; mainLaw: MainLaw; form: CompositionForm | null }
	// One thesis fixed for the drawing (step 4): written by the author, or one
	// of the four the AI proposed (with the digest of the request that proposed them).
	| { kind: 'thesis'; thesis: string; source: 'author' | 'proposed'; digest?: string };

/** What the dialog asks for (step 4c): one change, or the AI's four theses,
 *  which become four thesis changes once they are proposed. */
export type CompositionRequest = CompositionChange | { kind: 'proposed_theses' };

/** The longest thesis a run takes (the core's MAX_THESIS_CHARS). */
export const MAX_THESIS_CHARS = 400;

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
export function compositionChangeOptions(change: CompositionChange, parent: { form: string | null; mainLaw: string | null; thesis?: string | null }): {
	options: { composition_form?: CompositionForm; composition_main_law?: MainLaw; composition_thesis?: string;
		composition_thesis_source?: 'author' | 'proposed'; composition_thesis_prompt_digest?: string };
	metadata: Record<string, string | null>;
} {
	if (change.kind === 'thesis') {
		const thesis = change.thesis.trim();
		return {
			options: { composition_thesis: thesis, composition_thesis_source: change.source,
				...(change.source === 'proposed' && change.digest ? { composition_thesis_prompt_digest: change.digest } : {}) },
			metadata: { thesis_from: parent.thesis ?? null, thesis_to: thesis, thesis_source: change.source },
		};
	}
	if (change.kind === 'form') {
		return { options: { composition_form: change.form }, metadata: { form_from: parent.form, form_to: change.form } };
	}
	return {
		options: { ...(change.form ? { composition_form: change.form } : {}), composition_main_law: change.mainLaw },
		metadata: { main_law_from: parent.mainLaw, main_law_to: change.mainLaw, form: change.form },
	};
}

/** A thesis the author may fix: 1 to 400 characters once the spaces around it are dropped. */
export function thesisWritable(text: string): boolean {
	const thesis = text.trim();
	return thesis.length > 0 && [...thesis].length <= MAX_THESIS_CHARS;
}

/** The head of a thesis for a seat or an edge: its first characters, with "…" when it goes on. */
export function thesisHead(thesis: string, length = 14): string {
	const characters = [...thesis.trim()];
	return characters.length > length ? `${characters.slice(0, length).join('')}…` : characters.join('');
}
