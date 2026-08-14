// Picking up a batch that stopped part-way, kept apart from the drawing itself.
// paintOne() calls a model, so a test that drove a resumed run end to end would
// need an LLM; what actually decides the feature -- whether the last run reached
// the end of its prompt, which lines have no work, and what conditions those
// works were drawn under -- is arithmetic over a list and a listing, and is
// testable on its own. Same reason retry.ts is a module and not a closure.

/** One line of a batch prompt, numbered the way the run numbers it. */
export type NumberedLine = {
	/** 1-based index into the whole prompt, blank lines included. */
	line: number;
	input: string;
};

/**
 * The fields of a saved work this module reads. Structurally a subset of
 * HistoryItem, and deliberately not imported from it: that type lives beside
 * `$state`, and pulling it in would drag the Svelte compiler into node:test.
 */
export type BatchWork = {
	batch_line_number?: number | null;
	batch_run_id?: string | null;
	source_text?: string | null;
	input?: string | null;
	stage1_model?: string | null;
	stage2_model?: string | null;
	render_color_catalog_id?: string | null;
	catalog_id?: string | null;
	sketch_grain?: string | null;
	render_wild?: boolean | null;
	render_canvas_aspect_id?: string | null;
	render_canvas_aspect?: string | null;
};

/** The `#12 ` a batch run puts at the head of the description it stores. */
const BATCH_HEADER = /^#\d+\s+/;

/**
 * The lines a batch prompt paints, numbered as the run numbers them.
 *
 * `isPaintable` is lent by the caller because deciding it means cutting the
 * author's own numbering off the line, which is the pipeline's business and
 * lives with the pipeline. The numbering here counts every line of the prompt,
 * blank ones included -- that is what puts `#7` on the seventh line rather than
 * on the seventh work.
 */
export function numberedBatchLines(
	prompt: string,
	isPaintable: (input: string) => boolean,
): NumberedLine[] {
	return prompt
		.split('\n')
		.map((line, index) => ({ line: index + 1, input: line.trim() }))
		.filter((item) => isPaintable(item.input));
}

/** The newest work carrying a batch number header, or null if none does. */
export function latestBatchWork<T extends BatchWork>(works: readonly T[]): T | null {
	for (const work of works) {
		if (typeof work.batch_line_number === 'number' && work.batch_line_number > 0) return work;
	}
	return null;
}

/**
 * The description a batch work was painted from, without the `#N ` header.
 *
 * `source_text` is the line as the author wrote it; `input` is the same line
 * with the header the run prepended. Works saved before source_text existed
 * only have the latter, hence the fallback.
 */
export function batchWorkDescription(work: BatchWork): string {
	const source = work.source_text?.trim();
	if (source) return source;
	return (work.input ?? '').replace(BATCH_HEADER, '').trim();
}

/**
 * Whether the newest batch work says its run stopped before the end of the
 * prompt it came from.
 *
 * Both halves of the comparison matter. The number alone would call a run
 * unfinished whenever the author has since shortened the prompt, and the
 * description alone cannot tell the last line from any other. A work whose
 * number is absent from the prompt, or whose description is not the one on that
 * line, belongs to some other batch -- there is nothing here to resume.
 */
export function batchStoppedPartWay(
	lines: readonly NumberedLine[],
	work: BatchWork | null | undefined,
): boolean {
	if (lines.length === 0 || !work) return false;
	const number = work.batch_line_number;
	if (typeof number !== 'number') return false;
	const painted = lines.find((item) => item.line === number);
	if (!painted) return false;
	if (painted.input !== batchWorkDescription(work)) return false;
	return number !== lines[lines.length - 1].line;
}

/**
 * The lines of the prompt that have no work: what resuming paints.
 *
 * Not "everything after the last one painted": a line that failed mid-run
 * leaves a gap, and the works after it are already drawn. Painting what is
 * missing covers both the gap and the tail, and never draws the same line
 * twice. The smallest missing number is where the resumed run starts, and each
 * line keeps the number it had, so the works stay numbered by the prompt.
 *
 * `runId` scopes the listing to one run. When it is null -- works saved before
 * runs were identified -- every batch work in the listing counts, which can only
 * make the resumed run shorter, never make it repeat a line.
 */
export function linesToResume(
	lines: readonly NumberedLine[],
	works: readonly BatchWork[],
	runId: string | null,
): NumberedLine[] {
	const drawn = new Set<number>();
	for (const work of works) {
		if (typeof work.batch_line_number !== 'number') continue;
		if (runId !== null && (work.batch_run_id ?? null) !== runId) continue;
		drawn.add(work.batch_line_number);
	}
	return lines.filter((item) => !drawn.has(item.line));
}

/** What a work records about the conditions it was drawn under. */
export type BatchRunConditions = {
	stage1Model: string | null;
	stage2Model: string | null;
	catalogId: string | null;
	sketchGrain: string | null;
	wild: boolean | null;
	canvasAspectId: string | null;
};

/**
 * The conditions to put back before resuming, read off the last work drawn.
 *
 * Every field is null when the work does not record it, so a caller applies
 * what is there and leaves the rest of the current settings alone. A missing
 * value is not a value: `render_wild` absent means the work predates the switch,
 * not that the switch was off.
 */
export function conditionsOfWork(work: BatchWork): BatchRunConditions {
	return {
		stage1Model: work.stage1_model ?? null,
		stage2Model: work.stage2_model ?? null,
		catalogId: work.render_color_catalog_id ?? work.catalog_id ?? null,
		sketchGrain: work.sketch_grain ?? null,
		wild: typeof work.render_wild === 'boolean' ? work.render_wild : null,
		canvasAspectId: work.render_canvas_aspect_id ?? work.render_canvas_aspect ?? null,
	};
}
