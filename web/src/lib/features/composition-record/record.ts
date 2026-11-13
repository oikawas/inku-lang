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

/** A record a child shows from the ancestor it was drawn from without reading the description again (step 1d). */
export type InheritedComposition = {
	historyId: string;
	at: number | null;
	/** The edges walked, from the child up (the first is the child's own kind). */
	via: string[];
	record: CompositionRecord;
};

/**
 * The ancestor's record the Server adds to a work without its own
 * (`composition_inherited`: the answer and the requested form only). Read as
 * a used record so the same views show it; it never carries the colors.
 */
export function inheritedOf(work: { composition_inherited?: unknown } | null | undefined): InheritedComposition | null {
	const raw = work?.composition_inherited;
	if (!raw || typeof raw !== 'object') return null;
	const fields = raw as Record<string, unknown>;
	if (typeof fields.history_id !== 'string' || !fields.answer || typeof fields.answer !== 'object') return null;
	const via = Array.isArray(fields.via) ? fields.via.filter((kind): kind is string => typeof kind === 'string') : [];
	const record: CompositionRecord = { state: 'used', answer: fields.answer as CompositionRecord['answer'] };
	if (typeof fields.requested_form === 'string') record.requested_form = fields.requested_form;
	if (typeof fields.requested_main_law === 'string') record.requested_main_law = fields.requested_main_law;
	return { historyId: fields.history_id, at: typeof fields.at === 'number' ? fields.at : null, via, record };
}

/** The record a work shows: its own, else the one it inherited (marked as the parent's). */
export function shownRecordOf(work: { description_ddl?: unknown; composition_inherited?: unknown } | null | undefined): { record: CompositionRecord | null; inherited: InheritedComposition | null } {
	const own = compositionOf(work);
	if (own) return { record: own, inherited: null };
	const inherited = inheritedOf(work);
	return { record: inherited?.record ?? null, inherited };
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

/** What a card says about a drawn work or option: its record's state, thesis, form, main law and reason. */
export type CompositionSummary = {
	state: 'used' | 'fallback' | 'none';
	thesis: string | null;
	form: string | null;
	mainLaw: string | null;
	reason: string | null;
};

function textOrNull(value: unknown): string | null {
	return typeof value === 'string' && value.trim() ? value.trim() : null;
}

/** The summary of a record (2026-11-13: the refinement's option cards and the target beside them). */
export function compositionSummary(record: CompositionRecord | null | undefined): CompositionSummary {
	const shown = compositionShown(record);
	if (shown.kind !== 'used') return { state: shown.kind, thesis: null, form: null, mainLaw: null, reason: null };
	const answer = shown.record.answer;
	return {
		state: 'used',
		thesis: textOrNull(answer?.thesis),
		form: textOrNull(answer?.form),
		mainLaw: textOrNull(answer?.main_law),
		reason: textOrNull(answer?.reason)
	};
}

/** The summary of an option the refinement drew (its result carries the run's record). */
export function candidateComposition(result: { description_ddl?: unknown } | null | undefined): CompositionSummary {
	return compositionSummary(compositionOf(result));
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
