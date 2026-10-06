export type Rational = readonly [bigint, bigint];
export type RangeBounds = readonly [Rational, Rational, Rational, Rational];
export type RangePreview = { bounds: readonly [number, number, number, number]; invalid: boolean };
export type CompositionRange = { key: string; words: { ja: string; en: string }; bounds: RangeBounds; corner: boolean };
export type NumericRange = {
	start: number; end: number; nameStart: number; nameEnd: number;
	bodyStart: number; bodyEnd: number; name: string; body: string;
	lang: 'ja' | 'en'; bounds: RangeBounds | null;
};

function gcd(a: bigint, b: bigint): bigint {
	while (b) [a, b] = [b, a % b];
	return a;
}

export function parseRangeNumber(source: string, lang: 'ja' | 'en'): Rational | null {
	const text = (lang === 'ja' ? source.replace(/[０-９]/g, (digit) => String.fromCharCode(digit.charCodeAt(0) - 0xfee0)).replaceAll('．', '.').replaceAll('／', '/') : source).trim();
	if (text.length > 32) return null;
	let numerator: bigint;
	let denominator: bigint;
	if (/^\d+\/\d+$/.test(text)) {
		const [n, d] = text.split('/');
		numerator = BigInt(n.trim()); denominator = BigInt(d.trim());
		if (denominator < 1n || denominator > 1000000n) return null;
	} else if (/^\d+(?:\.\d{1,6})?$/.test(text)) {
		const [whole, fraction = ''] = text.split('.');
		denominator = 10n ** BigInt(fraction.length);
		numerator = BigInt(whole) * denominator + BigInt(fraction || '0');
	} else return null;
	if (numerator > denominator) return null;
	const divisor = gcd(numerator, denominator);
	return [numerator / divisor, denominator / divisor];
}

export function parseRangeBody(body: string, lang: 'ja' | 'en'): RangeBounds | null {
	const match = lang === 'ja'
		? /^\s*横\s*(.*?)\s*[〜～~－-]\s*(.*?)\s*[、，,]\s*縦\s*(.*?)\s*[〜～~－-]\s*(.*?)\s*$/.exec(body)
		: /^\s*horizontal\s+(.+?)(?:\s+to\s+|\s*[-–]\s*)(.+?)\s*,\s*vertical\s+(.+?)(?:\s+to\s+|\s*[-–]\s*)(.+?)\s*$/i.exec(body);
	if (!match) return null;
	const values = match.slice(1).map((value) => parseRangeNumber(value, lang));
	if (values.some((value) => value === null)) return null;
	const [left, right, top, bottom] = values as Rational[];
	if (left[0] * right[1] >= right[0] * left[1] || top[0] * bottom[1] >= bottom[0] * top[1]) return null;
	return [left, top, right, bottom];
}

export function sameBounds(a: RangeBounds, b: RangeBounds): boolean {
	return a.every(([n, d], i) => n * b[i][1] === b[i][0] * d);
}

export function rangePreview(bounds: RangeBounds, invalid = false): RangePreview {
	return { bounds: bounds.map(([n, d]) => Number(n) / Number(d)) as [number, number, number, number], invalid };
}

export function readCompositionRanges(payload: unknown): CompositionRange[] {
	if (!payload || typeof payload !== 'object') return [];
	const value = payload as { schema?: unknown; ranges?: unknown };
	if (value.schema !== 'inku.composition-ranges.v1' || !Array.isArray(value.ranges)) return [];
	const result: CompositionRange[] = [];
	for (const item of value.ranges) {
		if (!item || typeof item !== 'object') return [];
		const { key, words, bounds, corner } = item;
		if (typeof key !== 'string' || !words || typeof words.ja !== 'string' || !words.ja || typeof words.en !== 'string' || !words.en || typeof corner !== 'boolean' || !Array.isArray(bounds) || bounds.length !== 4) return [];
		if (!bounds.every((pair: unknown) => Array.isArray(pair) && pair.length === 2 && pair.every(Number.isSafeInteger) && pair[0] >= 0 && pair[1] > 0 && pair[0] <= pair[1])) return [];
		const exact = bounds.map(([n, d]: number[]) => [BigInt(n), BigInt(d)]) as unknown as RangeBounds;
		if (exact[0][0] * exact[2][1] >= exact[2][0] * exact[0][1] || exact[1][0] * exact[3][1] >= exact[3][0] * exact[1][1]) return [];
		result.push({ key, words, bounds: exact, corner });
	}
	return result;
}

export function scanNumericRanges(text: string): NumericRange[] {
	const result: NumericRange[] = [];
	const patterns: ['ja' | 'en', RegExp][] = [
		['ja', /(?:^|[\n。！？、，,を])([\t 　]*)([^\n。！？、，,を（）()]+?)([\t 　]*[（(])(横[^）)\n]*)([）)])(?=\s*に)/g],
		['en', /\b(?:at|in|on)\s+((?:\[composition\]\s*)?(?:the\s+)?[^()\n.,;]+?)(\s*\()(horizontal\s+[^)\n]*)(\))/gi]
	];
	for (const [lang, pattern] of patterns) {
		for (const match of text.matchAll(pattern)) {
			const rawName = lang === 'ja' ? match[2] : match[1];
			const opening = lang === 'ja' ? match[3] : match[2];
			const body = lang === 'ja' ? match[4] : match[3];
			const nameStart = match.index! + match[0].length - rawName.length - opening.length - body.length - 1;
			const nameEnd = nameStart + rawName.length;
			const bodyStart = nameEnd + opening.length;
			result.push({ start: nameStart, end: bodyStart + body.length + 1, nameStart, nameEnd, bodyStart, bodyEnd: bodyStart + body.length,
				name: rawName.replace(lang === 'ja' ? /^［構図］\s*/ : /^\[composition\]\s*/, '').replace(lang === 'en' ? /^the\s+/ : /$^/, '').trim(),
				body, lang, bounds: parseRangeBody(body, lang) });
		}
	}
	return result.sort((a, b) => a.start - b.start).filter((range, i, all) => !i || range.start >= all[i - 1].end);
}

export function matchingRange(range: NumericRange, ranges: CompositionRange[]): CompositionRange | undefined {
	return range.bounds ? ranges.find((entry) => entry.words[range.lang] === range.name && sameBounds(entry.bounds, range.bounds!)) : undefined;
}

export function followedName(bounds: RangeBounds | null, currentName: string, openedName: string, lang: 'ja' | 'en', ranges: readonly CompositionRange[]): string {
	if (!bounds) return currentName;
	const match = ranges.find((entry) => sameBounds(entry.bounds, bounds));
	if (match) return match.words[lang];
	const chosen = lang === 'ja' ? '指定の範囲' : 'chosen place';
	return openedName === chosen || ranges.some((entry) => entry.words[lang] === openedName) ? chosen : openedName;
}

export function editNumericRange(source: string, range: NumericRange, body: string, ranges: CompositionRange[], openedName = range.name): { source: string; range: NumericRange } {
	const bounds = parseRangeBody(body, range.lang);
	const rawName = source.slice(range.nameStart, range.nameEnd);
	const name = followedName(bounds, range.name, openedName, range.lang, ranges);
	const nextName = rawName.replace(range.name, name);
	const nextSource = source.slice(0, range.nameStart) + nextName + source.slice(range.nameEnd, range.bodyStart) + body + source.slice(range.bodyEnd);
	const shift = nextName.length - rawName.length;
	return { source: nextSource, range: { ...range, name, nameEnd: range.nameEnd + shift, bodyStart: range.bodyStart + shift,
		bodyEnd: range.bodyStart + shift + body.length, end: range.bodyStart + shift + body.length + 1, body, bounds } };
}
