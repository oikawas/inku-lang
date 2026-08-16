// How heavy a work the total ceiling allows, in megabytes of SVG.
//
// The stepper on the limits panel counts marks. Marks are a proxy for the thing
// that actually reaches a reader -- the weight of the file their browser opens
// -- and a proxy that is off by 25% depending on which tool drew them. An
// administrator raising the ceiling is entitled to know what they are raising it
// to, so the panel converts on the spot.
//
// The per-mark cost is not defined here. It is measured, it lives in the
// server's limits.py, and it arrives in the settings response: a second copy in
// the browser would be frozen on the day it was copied.

// The one field this answers for. The conversion belongs under the total, which
// is the number that decides the whole work; the other eight are per-instruction
// bounds, legibility thresholds, or typo guards, and a megabyte figure under any
// of them would be describing a quantity they do not govern.
export const WEIGHTED_LIMIT_FIELD = 'max_expanded_primitives';

export type MarkWeight = { low: number; high: number };

/** Megabytes one work may reach at `marks`, from the lightest tool to the heaviest. */
export function markWeight(
	field: string,
	marks: number | undefined,
	bytesPerMark: Record<string, number> | undefined
): MarkWeight | null {
	if (field !== WEIGHTED_LIMIT_FIELD) return null;
	if (!Number.isFinite(marks) || (marks as number) <= 0) return null;
	const costs = Object.values(bytesPerMark ?? {}).filter(
		(cost) => Number.isFinite(cost) && cost > 0
	);
	if (costs.length === 0) return null;
	const mb = (cost: number) => Math.round(((marks as number) * cost) / 1_000_000 * 10) / 10;
	return { low: mb(Math.min(...costs)), high: mb(Math.max(...costs)) };
}
