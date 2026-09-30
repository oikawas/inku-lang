/**
 * The verse form a description's length is nearest to, for the meter under
 * the description box and in the "change the description" dialog.
 *
 * The forms are counted in sounds (on), but the meter counts characters: a
 * kanji is read as one sound or several, and only its reading says which.
 * The total decides the form, not the line breaks, so a description written
 * as one line is judged the same as one set out 5-7-5.
 *
 * Sedōka (5-7-7 / 5-7-7) and bussokuseki-ka (5-7-5-7-7-7) are both 38, so a
 * total of 38 names both. Chōka is 5-7 repeated and closed by 7; with at least
 * three pairs it is 12n + 7 for n >= 3 (fewer pairs are katauta and tanka).
 * Plain .ts (no runes), so the rules are testable without the compiler.
 */

import { pipelineDescription } from './description-labels';

export type VerseForm = 'haiku' | 'katauta' | 'tanka' | 'sedoka-bussokuseki' | 'choka';

const FIXED_FORMS: ReadonlyArray<{ form: VerseForm; length: number }> = [
	{ form: 'haiku', length: 17 },
	{ form: 'katauta', length: 19 },
	{ form: 'tanka', length: 31 },
	{ form: 'sedoka-bussokuseki', length: 38 }
];

const CHOKA_FIRST_PAIRS = 3;
const chokaLength = (pairs: number): number => 12 * pairs + 7;

/** The form nearest to `count` characters, and that form's length. A tie goes to the shorter form. */
export function nearestVerseForm(count: number): { form: VerseForm; length: number } {
	const candidates = [...FIXED_FORMS];
	for (let pairs = CHOKA_FIRST_PAIRS; ; pairs += 1) {
		candidates.push({ form: 'choka', length: chokaLength(pairs) });
		if (chokaLength(pairs) >= count) break;
	}
	let best = candidates[0];
	for (const candidate of candidates) {
		if (Math.abs(count - candidate.length) < Math.abs(count - best.length)) best = candidate;
	}
	return best;
}

/** The English guide stays the one it was: twelve words, a tanka's worth. */
const ENGLISH_WORD_GUIDE = 12;

export type DescriptionMeter =
	| { unit: 'chars'; count: number; target: number; form: VerseForm; over: boolean }
	| { unit: 'words'; count: number; target: number; over: boolean };

/**
 * What the meter says about a description. It counts what the drawing will
 * read -- the author's numbering and comments are not the description -- and
 * leaves out white space. English is counted in words.
 */
export function describeLength(text: string, uiLang: string): DescriptionMeter {
	const source = pipelineDescription(text).trim();
	const asciiMostly = source.length > 0 && /^[\x00-\x7F\s.,;:!?()"-]+$/.test(source);
	const hasJapanese = /[぀-ヿ㐀-鿿]/.test(source);
	if (!hasJapanese && (asciiMostly || (!source && uiLang === 'en'))) {
		const count = (source.match(/[A-Za-z0-9]+(?:[-][A-Za-z0-9]+)*/g) ?? []).length;
		return { unit: 'words', count, target: ENGLISH_WORD_GUIDE, over: count > ENGLISH_WORD_GUIDE };
	}
	const count = Array.from(source.replace(/\s/g, '')).length;
	const { form, length } = nearestVerseForm(count);
	return { unit: 'chars', count, target: length, form, over: count > length };
}
