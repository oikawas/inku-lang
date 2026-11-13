// Reading a work's composition record (SPEC 12.6.7) for the screen: the
// thesis line above the canvas and the "composition and laws" section of the
// left panel (2026-11-13). Nothing here changes a record; a field another
// build wrote may be missing, so every field is read on its own.

import type { CompositionRecord } from '../../draw-route.ts';
import { atName, lawName, placeName } from './composition-names.ts';

type WorkWithRecord = { description_ddl?: unknown } | null | undefined;

/** The work's composition record, if it keeps one. */
export function compositionOf(work: WorkWithRecord): CompositionRecord | null {
	const record = work?.description_ddl;
	if (!record || typeof record !== 'object') return null;
	const composition = (record as { composition?: unknown }).composition;
	return composition && typeof composition === 'object' ? composition as CompositionRecord : null;
}

/** The thesis of a record the drawing used; none for a fallback or a record without one. */
export function thesisOf(record: CompositionRecord | null | undefined): string | null {
	if (record?.state !== 'used') return null;
	const thesis = record.answer?.thesis;
	return typeof thesis === 'string' && thesis.trim() ? thesis.trim() : null;
}

export type CompositionShown =
	| { kind: 'used'; record: CompositionRecord }
	| { kind: 'fallback'; record: CompositionRecord }
	| { kind: 'none' };

/** How the section shows a work: the whole record, the record that fell back, or no record. */
export function compositionShown(record: CompositionRecord | null | undefined): CompositionShown {
	if (record?.state === 'used' && record.answer) return { kind: 'used', record };
	if (record?.state === 'fallback') return { kind: 'fallback', record };
	return { kind: 'none' };
}

function fieldsOf(value: unknown): Record<string, unknown> {
	return value && typeof value === 'object' && !Array.isArray(value) ? value as Record<string, unknown> : {};
}

function thingNumbers(value: unknown): number[] {
	if (Number.isInteger(value)) return [value as number];
	return Array.isArray(value) ? value.filter((item): item is number => Number.isInteger(item)) : [];
}

/**
 * Where the laws put each thing, by thing number: a law's targets that name a
 * point (`at`, e.g. B1's crossings) and a card that names a spot (`spot`). A
 * thing a law only shapes or groups has no place. The first place wins.
 */
export function thingPlaces(answer: CompositionRecord['answer'], isJapanese: boolean): Map<number, string> {
	const places = new Map<number, string>();
	const put = (thing: number, place: string) => { if (!places.has(thing)) places.set(thing, place); };
	for (const [code, value] of Object.entries(fieldsOf(answer?.laws))) {
		const law = fieldsOf(value);
		for (const target of Array.isArray(law.targets) ? law.targets : []) {
			const fields = fieldsOf(target);
			if (typeof fields.at !== 'string') continue;
			const at = atName(fields.at, isJapanese);
			const place = isJapanese ? `${lawName(code, true)}・${at}` : `${lawName(code, false)}, ${at.charAt(0).toLowerCase()}${at.slice(1)}`;
			for (const thing of thingNumbers(fields.thing)) put(thing, place);
		}
		if (typeof law.spot === 'string') {
			const place = placeName(law.spot, isJapanese);
			for (const thing of thingNumbers(law.things ?? law.thing)) put(thing, place);
		}
	}
	return places;
}

function plain(text: string): string {
	return text.replace(/[\s　]+/g, '');
}

/** Whether the words a thing quotes are in the description (spaces aside); a thing whose words are not came from the reading. */
export function quoteInDescription(quote: string | null | undefined, description: string | null | undefined): boolean {
	if (!quote || !quote.trim()) return false;
	return plain(description ?? '').includes(plain(quote));
}
