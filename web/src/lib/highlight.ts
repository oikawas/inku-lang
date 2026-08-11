import { SAIJIKI, SAIJIKI_EN, type SaijikiCategory } from './saijiki';
import { scanPluginReferences, type PluginNameIndex } from './plugin-names';

export type Part = {
	text: string;
	// 'plugin-name' is a namespaced reference (`Nature.下草`) and only appears
	// when the caller hands over the list of names the server holds; without
	// it the reference is scanned as ordinary text, exactly as before.
	kind: 'saijiki' | 'emotion' | 'plain' | 'plugin-name';
	category?: string;
	categoryKey?: string;
	/** For 'plugin-name': whether the server holds this qualified name. */
	known?: boolean;
};

// SAIJIKI / SAIJIKI_EN are hydratable stores (reassigned on GET /api/saijiki).
// Rebuild the greedy-match entry list whenever either store reference changes,
// so annotate stays synchronous while picking up hydrated vocabulary. Both
// languages are matched at once: the DDL language follows instruction_lang and
// need not agree with the UI language.
type SaijikiEntry = { word: string; lower: string; category: string; categoryKey: string; ascii: boolean };
let entriesJaRef: SaijikiCategory[] | null = null;
let entriesEnRef: SaijikiCategory[] | null = null;
let entriesCache: SaijikiEntry[] = [];

// ASCII surfaces ("line", "pen", "dash-dot") must not match inside a longer
// word ("outline", "open"). Japanese surfaces have no such boundary.
const WORD_CHAR = /[A-Za-z0-9-]/;

function categoryEntries(categories: SaijikiCategory[], label: (cat: SaijikiCategory) => string): SaijikiEntry[] {
	return categories.flatMap((cat) =>
		cat.words.map((word) => ({
			word,
			lower: word.toLowerCase(),
			category: label(cat),
			categoryKey: cat.key,
			ascii: /^[\x20-\x7e]+$/.test(word)
		}))
	);
}

function saijikiEntries(): SaijikiEntry[] {
	if (entriesJaRef !== SAIJIKI || entriesEnRef !== SAIJIKI_EN) {
		entriesJaRef = SAIJIKI;
		entriesEnRef = SAIJIKI_EN;
		entriesCache = [
			...categoryEntries(SAIJIKI, (cat) => cat.label),
			...categoryEntries(SAIJIKI_EN, (cat) => cat.en)
		].sort((a, b) => b.word.length - a.word.length);
	}
	return entriesCache;
}

function matchesAt(text: string, index: number, entry: SaijikiEntry): boolean {
	if (!entry.ascii) return text.startsWith(entry.word, index);
	const end = index + entry.word.length;
	if (text.slice(index, end).toLowerCase() !== entry.lower) return false;
	if (index > 0 && WORD_CHAR.test(text[index - 1])) return false;
	if (end < text.length && WORD_CHAR.test(text[end])) return false;
	return true;
}

const EMOTION_WORDS = [
	'美しい',
	'美しく',
	'激しい',
	'激しく',
	'静かな',
	'静かに',
	'素敵',
	'きれい',
	'やさしい',
	'切ない',
	'哀しい',
	'儚い',
	'神秘的',
	'幻想的',
	'寂しい',
	'爽やか'
].sort((a, b) => b.length - a.length);

/**
 * 文字列を Saijiki / 感情語 / 地 の 3 種に分割。
 * 貪欲な最長一致で走査する。
 *
 * With a plugin name index, namespaced references are cut out first: they are
 * one word to the server, and letting the greedy saijiki match run inside them
 * splits `Nature.青葉` into a color word and two loose characters.
 */
export function annotate(text: string, pluginNames: PluginNameIndex | null = null): Part[] {
	const parts: Part[] = [];
	const references = pluginNames ? scanPluginReferences(text, pluginNames) : [];
	const referenceAt = new Map(references.map((reference) => [reference.start, reference]));
	let i = 0;

	const pushPlain = (ch: string) => {
		const last = parts[parts.length - 1];
		if (last && last.kind === 'plain') {
			last.text += ch;
		} else {
			parts.push({ text: ch, kind: 'plain' });
		}
	};

	while (i < text.length) {
		let matched = false;

		const reference = referenceAt.get(i);
		if (reference) {
			parts.push({ text: reference.text, kind: 'plugin-name', known: reference.known });
			i = reference.end;
			continue;
		}

		for (const entry of saijikiEntries()) {
			if (matchesAt(text, i, entry)) {
				parts.push({
					text: text.slice(i, i + entry.word.length),
					kind: 'saijiki',
					category: entry.category,
					categoryKey: entry.categoryKey
				});
				i += entry.word.length;
				matched = true;
				break;
			}
		}
		if (matched) continue;

		for (const word of EMOTION_WORDS) {
			if (text.startsWith(word, i)) {
				parts.push({ text: word, kind: 'emotion' });
				i += word.length;
				matched = true;
				break;
			}
		}
		if (matched) continue;

		pushPlain(text[i]);
		i += 1;
	}

	return parts;
}

function escapeHtml(value: string): string {
	return value
		.replaceAll('&', '&amp;')
		.replaceAll('<', '&lt;')
		.replaceAll('>', '&gt;');
}

// Color class per category. The key is language-neutral, so English surfaces
// get the same color as their Japanese counterparts; the label switch stays as
// the fallback for callers that only carry a label.
function saijikiCategoryClassByKey(key: string): string {
	if (key.startsWith('plugin-')) return 'plugin';
	switch (key) {
		case 'katachi': return 'shape';
		case 'tezawari': return 'touch';
		case 'tsuranari': return 'line';
		case 'iro': return 'color';
		case 'yuragi': return 'motion';
		case 'basho': return 'place';
		case 'ugoki': return 'action';
		case 'katamuki': return 'angle';
		case 'wariai': return 'ratio';
		default: return 'word';
	}
}

function saijikiCategoryClass(category: string | undefined): string {
	switch (category) {
		case 'かたち': return 'shape';
		case 'てざわり': return 'touch';
		case 'つらなり': return 'line';
		case 'いろ': return 'color';
		case 'ゆらぎ': return 'motion';
		case 'ばしょ': return 'place';
		case 'うごき': return 'action';
		case 'かたむき': return 'angle';
		case 'わりあい': return 'ratio';
		case 'Nature': return 'plugin';
		default: return 'word';
	}
}

function ddlCaretMarkup(): string {
	return '<span class="ddl-custom-caret"></span>';
}

function renderDDLPart(part: Part, caretOffset: number | null): string {
	const { text, kind, category, categoryKey } = part;
	const before = caretOffset === null ? text : text.slice(0, caretOffset);
	const after = caretOffset === null ? '' : text.slice(caretOffset);
	const content = caretOffset === null ? escapeHtml(text) : `${escapeHtml(before)}${ddlCaretMarkup()}${escapeHtml(after)}`;
	if (kind === 'plugin-name') {
		// A name the server does not hold is not an error -- plugins can be
		// installed later, and today's unknown name is tomorrow's word. The
		// class says "not on this server", and the palette says it in amber.
		const cls = part.known ? 'plugin' : 'unknown';
		return `<span class="ddl-token ddl-token-${cls}">${content}</span>`;
	}
	if (kind === 'saijiki') {
		const cls = categoryKey ? saijikiCategoryClassByKey(categoryKey) : saijikiCategoryClass(category);
		return `<span class="ddl-token ddl-token-${cls}">${content}</span>`;
	}
	if (kind === 'emotion') {
		return `<span class="ddl-token-emotion">${content}</span>`;
	}
	return content;
}

/**
 * DDL テキストを Saijiki / 感情語 で色分けした HTML を返す。
 * caretIndex を渡すとその位置にカスタムキャレット span を差し込む。
 *
 * `pluginNames` is optional on purpose: the viewers and the batch/demo
 * observers call this without one and must keep the output they had.
 */
export function highlightDDL(text: string, caretIndex: number | null = null, pluginNames: PluginNameIndex | null = null): string {
	const clampedCaret = caretIndex === null ? null : Math.max(0, Math.min(text.length, caretIndex));
	let offset = 0;
	const html = annotate(text, pluginNames).map((part) => {
		const nextOffset = offset + part.text.length;
		const localCaret = clampedCaret !== null
			&& clampedCaret >= offset
			&& (clampedCaret < nextOffset || (clampedCaret === text.length && clampedCaret === nextOffset))
			? clampedCaret - offset
			: null;
		const rendered = renderDDLPart(part, localCaret);
		offset = nextOffset;
		return rendered;
	}).join('');
	if (clampedCaret === text.length && text.length === 0) return ddlCaretMarkup();
	return html;
}

export type InterpretationFeedbackPart = {
	text: string;
	tone: 'strong' | 'medium' | 'weak';
};

function normalizedIncludes(haystack: string, needle: string): boolean {
	const n = needle.trim().toLowerCase();
	if (!n) return false;
	return haystack.toLowerCase().includes(n);
}

export function interpretationFeedback(text: string, ddl: string | null | undefined): InterpretationFeedbackPart[] {
	const source = text || '';
	const normalizedDdl = ddl || '';
	if (!source.trim() || !normalizedDdl.trim()) return [];
	return annotate(source).map((part) => {
		if (part.kind === 'saijiki' && (normalizedIncludes(normalizedDdl, part.text) || normalizedIncludes(normalizedDdl, part.category || ''))) {
			return { text: part.text, tone: 'strong' };
		}
		if (part.kind === 'saijiki') return { text: part.text, tone: 'medium' };
		if (part.kind === 'emotion') return { text: part.text, tone: 'medium' };
		if (part.text.trim().length >= 2 && normalizedIncludes(normalizedDdl, part.text)) return { text: part.text, tone: 'medium' };
		return { text: part.text, tone: 'weak' };
	});
}
