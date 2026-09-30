/**
 * The verse form a description is, for the meter under the description box
 * and in the "change the description" dialog. A form is named only when the
 * description is close to it; otherwise the meter gives the count alone.
 *
 * Japanese forms are counted in sounds (on), which the Server counts
 * (POST /api/description/mora): haiku or senryū 5-7-5 (17; the sounds do not
 * tell them apart), katauta 5-7-7 (19), dodoitsu 7-7-7-5 (26), tanka
 * 5-7-5-7-7 (31), sedōka 5-7-7-5-7-7 and bussokuseki-ka 5-7-5-7-7-7 (both 38),
 * and chōka, 5-7 repeated at least three times and closed by 7 (12n + 7 from
 * 43). A poem set out phrase by phrase (line breaks, spaces, 、) is judged by
 * its phrases, each within two sounds of the form's; otherwise by its total,
 * within two sounds -- extra and missing sounds (字余り・字足らず) are part
 * of the forms. At 38 without phrases both forms are named. Until the Server
 * answers, the meter counts characters and judges by the total alone.
 *
 * English forms are counted in lines, with syllables where the form is made
 * of them; the Server counts syllables with the CMU Pronouncing Dictionary
 * (POST /api/description/syllables) and the page estimates them until it
 * answers. Couplet 2 lines; three lines are a haiku at 17 syllables or fewer
 * and a tercet above; quatrain 4; cinquain 5 lines of 2-4-6-8-2 syllables,
 * each within one; sonnet 14, villanelle 19 and sestina 39 lines, each within
 * one line. One line is prose and names no form.
 *
 * Plain .ts (no runes), so the rules are testable without the compiler.
 */

import { pipelineDescription } from './description-labels';

export type VerseForm =
	| 'haiku-senryu' | 'katauta' | 'dodoitsu' | 'tanka'
	| 'sedoka' | 'bussokuseki' | 'sedoka-bussokuseki' | 'choka';

type Named<F> = { form: F; length: number };

/** Extra and missing sounds a form still carries, per phrase and in total. */
const SOUND_TOLERANCE = 2;

const PHRASE_PATTERNS: ReadonlyArray<{ form: VerseForm; phrases: readonly number[] }> = [
	{ form: 'haiku-senryu', phrases: [5, 7, 5] },
	{ form: 'katauta', phrases: [5, 7, 7] },
	{ form: 'dodoitsu', phrases: [7, 7, 7, 5] },
	{ form: 'tanka', phrases: [5, 7, 5, 7, 7] },
	{ form: 'sedoka', phrases: [5, 7, 7, 5, 7, 7] },
	{ form: 'bussokuseki', phrases: [5, 7, 5, 7, 7, 7] }
];

const CHOKA_FIRST_PAIRS = 3;
const chokaPhrases = (pairs: number): number[] => [...Array.from({ length: pairs }, () => [5, 7]).flat(), 7];
const sum = (values: readonly number[]): number => values.reduce((total, value) => total + value, 0);

/** The form a poem set out phrase by phrase is, or null when it is none of them. */
function formByPhrases(phrases: readonly number[]): Named<VerseForm> | null {
	if (phrases.length < 2) return null;
	const candidates = PHRASE_PATTERNS.filter((pattern) => pattern.phrases.length === phrases.length);
	if (phrases.length >= 2 * CHOKA_FIRST_PAIRS + 1 && phrases.length % 2 === 1) {
		candidates.push({ form: 'choka', phrases: chokaPhrases((phrases.length - 1) / 2) });
	}
	let best: { named: Named<VerseForm>; distance: number } | null = null;
	for (const candidate of candidates) {
		const gaps = candidate.phrases.map((expected, index) => Math.abs(phrases[index] - expected));
		if (gaps.some((gap) => gap > SOUND_TOLERANCE)) continue;
		if (Math.abs(sum(phrases) - sum(candidate.phrases)) > SOUND_TOLERANCE) continue;
		const distance = sum(gaps);
		if (!best || distance < best.distance) best = { named: { form: candidate.form, length: sum(candidate.phrases) }, distance };
	}
	return best?.named ?? null;
}

const TOTAL_FORMS: ReadonlyArray<Named<VerseForm>> = [
	{ form: 'haiku-senryu', length: 17 },
	{ form: 'katauta', length: 19 },
	{ form: 'dodoitsu', length: 26 },
	{ form: 'tanka', length: 31 },
	{ form: 'sedoka-bussokuseki', length: 38 }
];

/** The form whose length the total is within two sounds of, nearest first; a tie goes to the shorter. */
export function formByTotal(total: number): Named<VerseForm> | null {
	const candidates = [...TOTAL_FORMS];
	for (let pairs = CHOKA_FIRST_PAIRS; 12 * pairs + 7 <= total + SOUND_TOLERANCE; pairs += 1) {
		candidates.push({ form: 'choka', length: 12 * pairs + 7 });
	}
	let best: Named<VerseForm> | null = null;
	for (const candidate of candidates) {
		const distance = Math.abs(total - candidate.length);
		if (distance > SOUND_TOLERANCE) continue;
		if (!best || distance < Math.abs(total - best.length)) best = candidate;
	}
	return best;
}

/** The Japanese form: by the phrases when they are one, otherwise by the total. */
export function japaneseForm(total: number, phrases: readonly number[] | null): Named<VerseForm> | null {
	return (phrases ? formByPhrases(phrases) : null) ?? formByTotal(total);
}

export type EnglishForm = 'couplet' | 'haiku' | 'tercet' | 'quatrain' | 'cinquain' | 'sonnet' | 'villanelle' | 'sestina';

const ENGLISH_HAIKU_MAX_SYLLABLES = 17;
const CINQUAIN = [2, 4, 6, 8, 2];
const LONG_FORMS: ReadonlyArray<Named<EnglishForm>> = [
	{ form: 'sonnet', length: 14 },
	{ form: 'villanelle', length: 19 },
	{ form: 'sestina', length: 39 }
];

/** The English form of these lines, given each line's syllables, or null when it is none. */
export function englishForm(lineSyllables: readonly number[]): Named<EnglishForm> | null {
	const lines = lineSyllables.length;
	if (lines === 2) return { form: 'couplet', length: 2 };
	if (lines === 3) return { form: sum(lineSyllables) <= ENGLISH_HAIKU_MAX_SYLLABLES ? 'haiku' : 'tercet', length: 3 };
	if (lines === 4) return { form: 'quatrain', length: 4 };
	if (lines === 5) {
		return lineSyllables.every((syllables, index) => Math.abs(syllables - CINQUAIN[index]) <= 1)
			? { form: 'cinquain', length: 5 }
			: null;
	}
	return LONG_FORMS.find((named) => Math.abs(lines - named.length) <= 1) ?? null;
}

/** Syllables by vowel groups, less a silent final e: the page's estimate until the Server answers. */
export function englishSyllables(text: string): number {
	let total = 0;
	for (const raw of text.toLowerCase().match(/[a-z]+(?:'[a-z]+)*/g) ?? []) {
		let word = raw.replace(/'/g, '');
		if (word.length > 2 && word.endsWith('e') && !/[^aeiouy]le$/.test(word)) word = word.slice(0, -1);
		total += Math.max(1, (word.match(/[aeiouy]+/g) ?? []).length);
	}
	return total;
}

/** The Server's count of a Japanese description's sounds. */
export type MoraCount = { mora: number; phrases: number[]; unread: string[] };
/** The Server's count of an English description's syllables, line by line. */
export type SyllableCount = { syllables: number; lines: number[]; unknown: string[] };
/** Whether each language's form is judged (Settings > Other (server)). */
export type MeterSwitches = { japanese: boolean; english: boolean };

export type DescriptionMeter =
	| { unit: 'mora'; count: number; form: Named<VerseForm> | null; approximate: boolean }
	| { unit: 'chars'; count: number; form: Named<VerseForm> | null }
	| { unit: 'lines'; count: number; form: Named<EnglishForm> | null };

/** Whether the description is Japanese (counted in sounds) rather than English (in lines). */
export function readsAsJapanese(text: string, uiLang: string): boolean {
	const source = pipelineDescription(text).trim();
	if (/[぀-ヿ㐀-鿿]/.test(source)) return true;
	const asciiMostly = source.length > 0 && /^[\x00-\x7F\s.,;:!?()"'-]+$/.test(source);
	return !asciiMostly && !(source === '' && uiLang === 'en');
}

export type MeterAnswers = { mora?: MoraCount | null; syllables?: SyllableCount | null };

/**
 * What the meter says about a description. It reads what the drawing will
 * read -- the author's numbering and comments are not the description. The
 * answers are the Server's counts of this text, when they have come.
 */
export function describeLength(
	text: string,
	uiLang: string,
	switches: MeterSwitches,
	answers: MeterAnswers = {}
): DescriptionMeter {
	const source = pipelineDescription(text).trim();
	if (!readsAsJapanese(text, uiLang)) {
		const lines = source.split('\n').map((line) => line.trim()).filter(Boolean);
		if (!switches.english) return { unit: 'lines', count: lines.length, form: null };
		const syllables = answers.syllables?.lines.length === lines.length
			? answers.syllables.lines
			: lines.map(englishSyllables);
		return { unit: 'lines', count: lines.length, form: englishForm(syllables) };
	}
	const chars = Array.from(source.replace(/\s/g, '')).length;
	if (!switches.japanese) return { unit: 'chars', count: chars, form: null };
	const mora = answers.mora;
	if (mora) {
		return { unit: 'mora', count: mora.mora, form: japaneseForm(mora.mora, mora.phrases), approximate: mora.unread.length > 0 };
	}
	return { unit: 'chars', count: chars, form: formByTotal(chars) };
}
