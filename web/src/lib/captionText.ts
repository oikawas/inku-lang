import { labelSegments } from './description-labels';

export type CaptionPart = {
	text: string;
	italic: boolean;
};

const REFINEMENT_DIRECTION = /^[ \t　]*(?:推敲方針|Refinement direction)[ \t　]*[:：]/;

function pushPart(parts: CaptionPart[], text: string, italic: boolean): void {
	if (!text) return;
	const last = parts[parts.length - 1];
	if (last?.italic === italic) last.text += text;
	else parts.push({ text, italic });
}

/** Split a displayed headnote into safely renderable text and emphasis.
 *
 * Comment boundaries come from the same UI parser that shades them in the
 * editor. Only the text inside the brackets is italic; the brackets remain
 * ordinary punctuation. A refinement direction is appended as its own line by
 * AIRefineModal, so the whole labelled line is italic in either UI language.
 */
export function captionParts(text: string): CaptionPart[] {
	const parts: CaptionPart[] = [];
	for (const line of String(text ?? '').split(/(\r?\n)/)) {
		if (line === '\n' || line === '\r\n') {
			pushPart(parts, line, false);
			continue;
		}
		if (REFINEMENT_DIRECTION.test(line)) {
			pushPart(parts, line, true);
			continue;
		}
		for (const segment of labelSegments(line)) {
			if (segment.kind !== 'comment' || segment.text.length < 2) {
				pushPart(parts, segment.text, false);
				continue;
			}
			pushPart(parts, segment.text.slice(0, 1), false);
			pushPart(parts, segment.text.slice(1, -1), true);
			pushPart(parts, segment.text.slice(-1), false);
		}
	}
	return parts;
}
