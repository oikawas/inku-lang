// Joining a work's things to its drawing, its instructions and its caption
// (2026-11-13, step 1c). The Server answers, for each chunk of the DDL, the
// thing it draws, the lines it holds and the box its placed sentences cover
// (GET /api/history/{id}/composition-boxes, the shared core's `boxes`). These
// are the pure parts: reading the answer, finding the thing under a point, the
// lines to light and the words of the caption to light.

export type Box = readonly [number, number, number, number];

/** The frame the drawing shows around the thing pointed at: its box and "2 磯の岩肌". */
export type ThingFrame = { box: Box; label: string };

/** One chunk of the DDL: its title, the thing it draws, its lines (from 0) and its box. */
export type ThingUnit = {
	title: string | null;
	thing: number | null;
	lines: number[];
	box: Box | null;
	/** Each of the nine places' outcome for this chunk (step 3): ok, clamped, or why it cannot move there. */
	places: Readonly<Record<string, string>>;
};

function isBox(value: unknown): value is Box {
	return Array.isArray(value) && value.length === 4 && value.every((n) => typeof n === 'number' && Number.isFinite(n));
}

/** The units of an answer; anything malformed is left out rather than guessed. */
export function readUnits(body: unknown): ThingUnit[] {
	const units = (body && typeof body === 'object' ? (body as { units?: unknown }).units : null);
	if (!Array.isArray(units)) return [];
	return units.flatMap((unit) => {
		if (!unit || typeof unit !== 'object') return [];
		const fields = unit as Record<string, unknown>;
		const lines = Array.isArray(fields.lines) ? fields.lines.filter((n): n is number => Number.isInteger(n) && (n as number) >= 0) : [];
		return [{
			title: typeof fields.title === 'string' ? fields.title : null,
			thing: Number.isInteger(fields.thing) ? fields.thing as number : null,
			lines,
			box: isBox(fields.box) ? fields.box : null,
			places: fields.places && typeof fields.places === 'object'
				? Object.fromEntries(Object.entries(fields.places as Record<string, unknown>)
					.filter((entry): entry is [string, string] => typeof entry[1] === 'string'))
				: {}
		}];
	});
}

/** The thing whose box holds the point (fractions of the paper); the smallest box wins. */
export function thingAt(units: readonly ThingUnit[], x: number, y: number): number | null {
	let best: { thing: number; area: number } | null = null;
	for (const unit of units) {
		if (unit.thing === null || !unit.box) continue;
		const [x0, y0, x1, y1] = unit.box;
		if (x < x0 || x > x1 || y < y0 || y > y1) continue;
		const area = (x1 - x0) * (y1 - y0);
		if (!best || area < best.area) best = { thing: unit.thing, area };
	}
	return best?.thing ?? null;
}

/** The lines (from 0) a thing's chunks hold, in order. */
export function thingLines(units: readonly ThingUnit[], thing: number | null): number[] {
	if (thing === null) return [];
	return [...new Set(units.filter((unit) => unit.thing === thing).flatMap((unit) => unit.lines))].sort((a, b) => a - b);
}

/** The thing whose chunk holds a line (from 0). */
export function thingOfLine(units: readonly ThingUnit[], line: number): number | null {
	return units.find((unit) => unit.thing !== null && unit.lines.includes(line))?.thing ?? null;
}

/** The union of a thing's boxes, if any of its chunks has one. */
export function thingBox(units: readonly ThingUnit[], thing: number | null): Box | null {
	const boxes = units.filter((unit) => unit.thing === thing && unit.box).map((unit) => unit.box as Box);
	if (thing === null || boxes.length === 0) return null;
	return [Math.min(...boxes.map((b) => b[0])), Math.min(...boxes.map((b) => b[1])), Math.max(...boxes.map((b) => b[2])), Math.max(...boxes.map((b) => b[3]))];
}

/** Where a thing's quoted words stand in the caption, spaces aside; null when they are not in it. */
export function quoteSpan(text: string, quote: string | null | undefined): { start: number; end: number } | null {
	const words = (quote ?? '').replace(/[\s　]+/g, '');
	if (!words) return null;
	// The caption without its spaces, with where each kept character stood.
	const offsets: number[] = [];
	let plain = '';
	let at = 0;
	for (const char of text) {
		if (!/[\s　]/.test(char)) { plain += char; offsets.push(at); }
		at += char.length;
	}
	const found = plain.indexOf(words);
	if (found < 0) return null;
	const wordChars = [...words].length;
	const plainIndex = [...plain.slice(0, found)].length;
	const start = offsets[plainIndex];
	const last = offsets[plainIndex + wordChars - 1];
	return { start, end: last + String.fromCodePoint(text.codePointAt(last) ?? 0).length };
}

/** Answers come back in any order: only the latest request may set the units. */
export class LatestRequest {
	private latest = 0;
	/** A token for a new request; any earlier token is now stale. */
	begin(): number { return ++this.latest; }
	/** Whether a request's answer may still be applied. */
	current(token: number): boolean { return token === this.latest; }
	/** Makes every request in flight stale (the work changed, or nothing is shown). */
	reset(): void { this.latest += 1; }
}
