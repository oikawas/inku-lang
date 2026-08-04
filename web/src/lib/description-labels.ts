/**
 * The ranges of a description the drawing does not read.
 *
 * The rule is enforced on the server (`server/src/inku_server/description_labels.py`);
 * this is the editor's copy, and it exists only so the author can see which
 * ranges will be dropped.  Because the rule now lives in two languages, both
 * read the same corpus: `server/tests/data/description-label-cases.json`.
 * Change one side and description-labels.test.ts turns red.
 */

export type LabelSpanKind = 'number' | 'comment';

export type LabelSpan = {
	start: number;
	end: number;
	kind: LabelSpanKind;
};

// Digits of either width, then a separator an author actually types.  The
// ideographic space counts as one, because "１　花" is how a numbered line is
// written in Japanese; a plain space does not, or "3 本の線" would lose its 3.
const LEADING_NUMBER = /^[ \t]*[0-9０-９]+[.．、)）:：　][ \t　]*/;

// Brackets of either width, closed on the line they were opened on.  An
// unclosed "[" is description: it would otherwise swallow the rest of the text.
const COMMENT = /\[[^[\]\n]*\]|［[^［］\n]*］/g;

/** Every range the drawing does not read, in order of appearance. */
export function excludedSpans(text: string): LabelSpan[] {
	if (!text) return [];
	const spans: LabelSpan[] = [];
	let offset = 0;
	// Keep the line breaks: the offsets are into the original string.
	for (const line of text.split('\n')) {
		const number = LEADING_NUMBER.exec(line);
		if (number) spans.push({ start: offset, end: offset + number[0].length, kind: 'number' });
		COMMENT.lastIndex = 0;
		let comment: RegExpExecArray | null;
		while ((comment = COMMENT.exec(line)) !== null) {
			spans.push({ start: offset + comment.index, end: offset + comment.index + comment[0].length, kind: 'comment' });
		}
		offset += line.length + 1; // + the "\n" that split() removed
	}
	spans.sort((a, b) => a.start - b.start);
	return spans;
}

export type LabelSegment = {
	text: string;
	kind: LabelSpanKind | null;
};

/**
 * The text split into what the drawing reads and what it does not, in order.
 * The editor paints a background behind every segment that has a kind.
 */
export function labelSegments(text: string): LabelSegment[] {
	const spans = excludedSpans(text);
	if (spans.length === 0) return text ? [{ text, kind: null }] : [];
	const segments: LabelSegment[] = [];
	let at = 0;
	for (const span of spans) {
		if (span.start > at) segments.push({ text: text.slice(at, span.start), kind: null });
		segments.push({ text: text.slice(span.start, span.end), kind: span.kind });
		at = span.end;
	}
	if (at < text.length) segments.push({ text: text.slice(at), kind: null });
	return segments;
}

/**
 * What the server will read.  The editor does not send this -- the server cuts
 * for every client -- but the character meter counts it, because the guide is
 * about the description, not about the author's numbering.
 */
export function pipelineDescription(text: string): string {
	if (!text) return text ?? '';
	const spans = excludedSpans(text);
	if (spans.length === 0) return text;
	const kept: string[] = [];
	let at = 0;
	for (const span of spans) {
		kept.push(text.slice(at, span.start));
		at = span.end;
	}
	kept.push(text.slice(at));
	return kept
		.join('')
		.split('\n')
		.map((line) => line.replace(/[ \t　]{2,}/g, ' ').replace(/^[ \t　]+|[ \t　]+$/g, ''))
		.join('\n');
}
