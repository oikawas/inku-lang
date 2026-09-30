/**
 * The verse form a description is nearest to, for the meter under the
 * description box and in the "change the description" dialog.
 *
 * Japanese forms are counted in sounds (on): haiku 5-7-5 is 17, katauta 19,
 * tanka 31, sedōka (5-7-7 / 5-7-7) and bussokuseki-ka (5-7-5-7-7-7) both 38,
 * and chōka -- 5-7 repeated and closed by 7, with at least three pairs -- is
 * 12n + 7 from 43. The Server counts the sounds (POST /api/description/mora);
 * until it answers, or when it cannot, the meter counts characters instead.
 * At 38 the phrases tell sedōka from bussokuseki-ka when the poem is set out
 * phrase by phrase; otherwise both are named.
 *
 * English forms are counted in lines: couplet 2, haiku or tercet 3, quatrain
 * 4, cinquain 5, sonnet 14, villanelle 19, sestina 39. Three lines are a haiku
 * when they are short (at most 17 syllables, counted roughly), a tercet
 * otherwise.
 *
 * Plain .ts (no runes), so the rules are testable without the compiler.
 */

import { pipelineDescription } from './description-labels';

export type VerseForm = 'haiku' | 'katauta' | 'tanka' | 'sedoka' | 'bussokuseki' | 'sedoka-bussokuseki' | 'choka';

type Nearest<F> = { form: F; length: number };

/** The candidate nearest to `count`; a tie goes to the shorter. `candidates` ascend. */
function nearest<F>(count: number, candidates: ReadonlyArray<Nearest<F>>): Nearest<F> {
	let best = candidates[0];
	for (const candidate of candidates) {
		if (Math.abs(count - candidate.length) < Math.abs(count - best.length)) best = candidate;
	}
	return best;
}

const FIXED_FORMS: ReadonlyArray<Nearest<VerseForm>> = [
	{ form: 'haiku', length: 17 },
	{ form: 'katauta', length: 19 },
	{ form: 'tanka', length: 31 },
	{ form: 'sedoka-bussokuseki', length: 38 }
];

const CHOKA_FIRST_PAIRS = 3;
const chokaLength = (pairs: number): number => 12 * pairs + 7;

/** The Japanese form nearest to `count` sounds (or characters), and its length. */
export function nearestVerseForm(count: number): Nearest<VerseForm> {
	const candidates = [...FIXED_FORMS];
	for (let pairs = CHOKA_FIRST_PAIRS; ; pairs += 1) {
		candidates.push({ form: 'choka', length: chokaLength(pairs) });
		if (chokaLength(pairs) >= count) break;
	}
	return nearest(count, candidates);
}

const SEDOKA = [5, 7, 7, 5, 7, 7];
const BUSSOKUSEKI = [5, 7, 5, 7, 7, 7];
const samePhrases = (a: readonly number[], b: readonly number[]): boolean =>
	a.length === b.length && a.every((value, index) => value === b[index]);

/** As nearestVerseForm, and at 38 the phrases name the one form they are. */
export function verseFormOfSounds(total: number, phrases: readonly number[]): Nearest<VerseForm> {
	const found = nearestVerseForm(total);
	if (found.form !== 'sedoka-bussokuseki' || total !== found.length) return found;
	if (samePhrases(phrases, SEDOKA)) return { form: 'sedoka', length: found.length };
	if (samePhrases(phrases, BUSSOKUSEKI)) return { form: 'bussokuseki', length: found.length };
	return found;
}

export type EnglishForm = 'couplet' | 'haiku' | 'tercet' | 'quatrain' | 'cinquain' | 'sonnet' | 'villanelle' | 'sestina';

const ENGLISH_FORMS: ReadonlyArray<Nearest<EnglishForm>> = [
	{ form: 'couplet', length: 2 },
	{ form: 'tercet', length: 3 },
	{ form: 'quatrain', length: 4 },
	{ form: 'cinquain', length: 5 },
	{ form: 'sonnet', length: 14 },
	{ form: 'villanelle', length: 19 },
	{ form: 'sestina', length: 39 }
];

/** An English haiku keeps near 5-7-5 and often under it; three longer lines are a tercet. */
const ENGLISH_HAIKU_MAX_SYLLABLES = 17;

/** Syllables by vowel groups, less a silent final e: rough, and enough to tell a haiku from a tercet. */
export function englishSyllables(text: string): number {
	let total = 0;
	for (const raw of text.toLowerCase().match(/[a-z]+/g) ?? []) {
		let word = raw;
		if (word.length > 2 && word.endsWith('e') && !/[^aeiouy]le$/.test(word)) word = word.slice(0, -1);
		total += Math.max(1, (word.match(/[aeiouy]+/g) ?? []).length);
	}
	return total;
}

/** The English form nearest to the description's lines, and its line count. */
export function nearestEnglishForm(lines: readonly string[]): Nearest<EnglishForm> {
	const found = nearest(lines.length, ENGLISH_FORMS);
	if (found.form === 'tercet' && lines.length === 3 && englishSyllables(lines.join(' ')) <= ENGLISH_HAIKU_MAX_SYLLABLES) {
		return { form: 'haiku', length: 3 };
	}
	return found;
}

/** The Server's count of a description's sounds. */
export type MoraCount = { mora: number; phrases: number[]; unread: string[] };

export type DescriptionMeter =
	| { unit: 'mora'; count: number; target: number; form: VerseForm; approximate: boolean; over: boolean }
	| { unit: 'chars'; count: number; target: number; form: VerseForm; over: boolean }
	| { unit: 'lines'; count: number; target: number; form: EnglishForm; over: boolean };

/** Whether the description is Japanese, so its sounds are worth asking the Server for. */
export function readsAsJapanese(text: string, uiLang: string): boolean {
	const source = pipelineDescription(text).trim();
	if (/[぀-ヿ㐀-鿿]/.test(source)) return true;
	const asciiMostly = source.length > 0 && /^[\x00-\x7F\s.,;:!?()"'-]+$/.test(source);
	return !asciiMostly && !(source === '' && uiLang === 'en');
}

/**
 * What the meter says about a description. It reads what the drawing will
 * read -- the author's numbering and comments are not the description.
 * `mora` is the Server's count of this text, or null while there is none.
 */
export function describeLength(text: string, uiLang: string, mora: MoraCount | null = null): DescriptionMeter {
	const source = pipelineDescription(text).trim();
	if (!readsAsJapanese(text, uiLang)) {
		const lines = source.split('\n').map((line) => line.trim()).filter(Boolean);
		const { form, length } = nearestEnglishForm(lines);
		return { unit: 'lines', count: lines.length, target: length, form, over: lines.length > length };
	}
	if (mora) {
		const { form, length } = verseFormOfSounds(mora.mora, mora.phrases);
		return { unit: 'mora', count: mora.mora, target: length, form, approximate: mora.unread.length > 0, over: mora.mora > length };
	}
	const count = Array.from(source.replace(/\s/g, '')).length;
	const { form, length } = nearestVerseForm(count);
	return { unit: 'chars', count, target: length, form, over: count > length };
}
