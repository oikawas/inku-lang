// The library "by description" (step 1e, 2026-11-13): a description's works
// laid out in columns by the form their composition took, in the names
// table's order, then a last column for the works without a record. A child
// that shows its ancestor's composition (step 1d) stands in its ancestor's
// column, marked. A mirror only: no shares, ranks or charts.

import { formIds } from '../composition-record/composition-names.ts';
import { shownRecordOf } from '../composition-record/record.ts';

type Work = { at?: number | null; description_ddl?: unknown; composition_inherited?: unknown };

/** The form column a work stands in, its main law, and the kind it inherits its record through. */
export function workComposition(work: Work): { form: string | null; mainLaw: string | null; inheritedVia: string | null } {
	const { record, inherited } = shownRecordOf(work);
	const answer = record?.state === 'used' ? record.answer ?? null : null;
	const text = (value: unknown) => (typeof value === 'string' && value.trim() ? value.trim() : null);
	return { form: text(answer?.form), mainLaw: text(answer?.main_law), inheritedVia: inherited ? inherited.via[0] ?? null : null };
}

export type DescriptionColumn<T> = { form: string | null; items: T[] };

/** The columns of one description's works: known forms in table order, then other forms, then no record (form null). Oldest first in a column. */
export function descriptionColumns<T extends Work>(items: readonly T[]): DescriptionColumn<T>[] {
	const byForm = new Map<string | null, T[]>();
	for (const item of items) {
		const form = workComposition(item).form;
		byForm.set(form, [...(byForm.get(form) ?? []), item]);
	}
	const known = formIds();
	const order = [...known.filter((form) => byForm.has(form)),
		...[...byForm.keys()].filter((form): form is string => form !== null && !known.includes(form)).sort(),
		...(byForm.has(null) ? [null] : [])];
	return order.map((form) => ({ form, items: [...(byForm.get(form) ?? [])].sort((a, b) => (a.at ?? 0) - (b.at ?? 0)) }));
}
