/**
 * The canvas ratio a DDL declares (「画面比W:H。」 / `Aspect ratio W:H.`, DDL 26)
 * and the ratio of a canvas format. The core reads the declaration; the screen
 * reads it only to ask whether a work moving to another paper is fitted into it.
 */
import { getCanvasAspectOption, type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';

export type CanvasRatio = { width: number; height: number };

const MAX_UNITS = 10_000;
const DECLARATION = /^\s*(?:画面比|aspect\s+ratio)\s*([0-9０-９]{1,5})\s*[:：]\s*([0-9０-９]{1,5})\s*$/i;

function units(text: string): number {
	return Number(text.replace(/[０-９]/g, (digit) => String(digit.charCodeAt(0) - 0xff10)));
}

/** A positive ratio in lowest terms, or null when a term is out of range. */
export function reducedCanvasRatio(width: number, height: number): CanvasRatio | null {
	if (!Number.isInteger(width) || !Number.isInteger(height)) return null;
	if (width < 1 || height < 1 || width > MAX_UNITS || height > MAX_UNITS) return null;
	let [a, b] = [width, height];
	while (b !== 0) [a, b] = [b, a % b];
	return { width: width / a, height: height / a };
}

/** The ratio of the DDL's first whole declaration sentence, or null. */
export function declaredCanvasRatio(ddl: string | null | undefined): CanvasRatio | null {
	for (const sentence of (ddl ?? '').split(/[。.！!？?\n]/)) {
		const match = DECLARATION.exec(sentence);
		if (match) {
			const ratio = reducedCanvasRatio(units(match[1]), units(match[2]));
			if (ratio) return ratio;
		}
	}
	return null;
}

/** The registry ratio of a canvas format. */
export function canvasRatioOfAspect(aspectId: CanvasAspectId): CanvasRatio | null {
	const option = getCanvasAspectOption(aspectId);
	return reducedCanvasRatio(option.ratioW, option.ratioH);
}

export function sameCanvasRatio(left: CanvasRatio, right: CanvasRatio): boolean {
	return left.width === right.width && left.height === right.height;
}

export function canvasRatioLabel(ratio: CanvasRatio): string {
	return `${ratio.width}:${ratio.height}`;
}
