import { SAIJIKI } from './saijiki';

export type Part = {
	text: string;
	kind: 'saijiki' | 'emotion' | 'plain';
	category?: string;
};

// SAIJIKI is a hydratable store (reassigned on GET /api/saijiki). Rebuild the
// greedy-match entry list whenever the store reference changes, so annotate
// stays synchronous while picking up hydrated vocabulary.
type SaijikiEntry = { word: string; category: string };
let entriesRef: typeof SAIJIKI | null = null;
let entriesCache: SaijikiEntry[] = [];

function saijikiEntries(): SaijikiEntry[] {
	if (entriesRef !== SAIJIKI) {
		entriesRef = SAIJIKI;
		entriesCache = SAIJIKI.flatMap((cat) =>
			cat.words.map((word) => ({ word, category: cat.label }))
		).sort((a, b) => b.word.length - a.word.length);
	}
	return entriesCache;
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
 */
export function annotate(text: string): Part[] {
	const parts: Part[] = [];
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

		for (const entry of saijikiEntries()) {
			if (text.startsWith(entry.word, i)) {
				parts.push({
					text: entry.word,
					kind: 'saijiki',
					category: entry.category
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

function renderDDLPart(text: string, kind: string, category: string | undefined, caretOffset: number | null): string {
	const before = caretOffset === null ? text : text.slice(0, caretOffset);
	const after = caretOffset === null ? '' : text.slice(caretOffset);
	const content = caretOffset === null ? escapeHtml(text) : `${escapeHtml(before)}${ddlCaretMarkup()}${escapeHtml(after)}`;
	if (kind === 'saijiki') {
		return `<span class="ddl-token ddl-token-${saijikiCategoryClass(category)}">${content}</span>`;
	}
	if (kind === 'emotion') {
		return `<span class="ddl-token-emotion">${content}</span>`;
	}
	return content;
}

/**
 * DDL テキストを Saijiki / 感情語 で色分けした HTML を返す。
 * caretIndex を渡すとその位置にカスタムキャレット span を差し込む。
 */
export function highlightDDL(text: string, caretIndex: number | null = null): string {
	const clampedCaret = caretIndex === null ? null : Math.max(0, Math.min(text.length, caretIndex));
	let offset = 0;
	const html = annotate(text).map((part) => {
		const nextOffset = offset + part.text.length;
		const localCaret = clampedCaret !== null
			&& clampedCaret >= offset
			&& (clampedCaret < nextOffset || (clampedCaret === text.length && clampedCaret === nextOffset))
			? clampedCaret - offset
			: null;
		const rendered = renderDDLPart(part.text, part.kind, part.category, localCaret);
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
