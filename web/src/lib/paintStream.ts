// The NDJSON stream of /api/paint/stream, and the one place that decides which
// stage the running indicator names and how it counts the model's attempts.
//
// A drawing passes through four layers -- sketch from life (Stage 0.5),
// interpretation (Stage 1), the score (Stage 2) and the performance -- and the
// stream now writes an event as each of the first three settles. The page used
// to guess: it showed "interpreting" from the moment the request left, so the
// first half of the wait was labelled with the layer after the one actually
// working. Reading the events instead means the label is never ahead of the
// work.
//
// This module holds no page state on purpose. The label is chosen by one pure
// function and the handlers are built by one factory, so a test can drive the
// whole sequence and see both the wording and the wiring; a switch made inline
// in the page would be visible to no test at all.

import type { LangPack } from './i18n/types.ts';
import type { PipelineProviderAttempt } from './features/pipeline/api.ts';
import { ConnectionFailure, isAbort } from './transport/connection-failure.ts';

export type PaintSketchEvent = {
	event: 'sketch';
	sketch_state: string;
	grain: string;
	fallback_used: boolean;
	tokens_in: number | null;
	tokens_out: number | null;
	elapsed_ms: number;
};

export type PaintStage1Event = {
	event: 'stage1';
	ddl: string;
	thinking: string | null;
	stage1_model: string;
	stage2_model: string;
	tokens_in: number | null;
	tokens_out: number | null;
	elapsed_ms: number;
	interpret_fallback_used: boolean;
};

export type PaintScoreEvent = {
	event: 'score';
	instruction_count: number;
	stage2_model: string;
	tokens_in: number | null;
	tokens_out: number | null;
	elapsed_ms: number;
};

/** The attempt that began, or null once the last one has ended. */
export type PaintAttemptEvent = {
	event: 'attempt';
	provider_attempt: Pick<PipelineProviderAttempt, 'action' | 'attempt' | 'max_attempts' | 'asked_again'> | null;
	elapsed_ms: number;
};

/**
 * What the running indicator counts: this attempt of at most so many. The
 * call's action, when the run reports it, lets the indicator name the
 * composition reading and the laws stage (`runningStageLabel`).
 */
export type ProviderAttemptCount = Pick<PipelineProviderAttempt, 'attempt' | 'max_attempts' | 'asked_again'> &
	Partial<Pick<PipelineProviderAttempt, 'action'>>;

export type PaintStreamHandlers = {
	/** Stage 0.5 settled. Absent from a run where the layer did not contribute. */
	onSketch?: (event: PaintSketchEvent) => void;
	/** Interpretation finished, before the score is written. */
	onStage1?: (event: PaintStage1Event) => void;
	/** The Score is final; the rest of the wait is the performance. */
	onScore?: (event: PaintScoreEvent) => void;
	/** A model call began or, with null, the last one ended. */
	onAttempt?: (event: PaintAttemptEvent) => void;
	/**
	 * Turns an in-band error event into the message the reader sees. The page
	 * owns that wording (it reads the language pack and the provider failure
	 * shapes), so it is handed in rather than duplicated here.
	 */
	describeError: (detail: unknown, status: number) => string;
};

/**
 * Consume the NDJSON stream of /api/paint/stream.
 *
 * The done event carries the same payload the non-streaming /api/paint
 * returns, and is the value this resolves to.
 *
 * An event this build does not know is read and dropped. That is deliberate:
 * the server may name a layer before the page learns the word for it, and a
 * page that threw on the unknown line would turn every such addition into a
 * broken draw.
 */
export async function readPaintStream<T>(
	response: Response,
	handlers: PaintStreamHandlers
): Promise<T> {
	const reader = response.body?.getReader();
	if (!reader) throw new Error('paint stream is not readable');
	const decoder = new TextDecoder();
	let buffer = '';
	let done: T | null = null;
	const consumeLine = (line: string): void => {
		if (!line) return;
		const event = JSON.parse(line) as { event: string } & Record<string, unknown>;
		if (event.event === 'sketch') {
			handlers.onSketch?.(event as unknown as PaintSketchEvent);
		} else if (event.event === 'stage1') {
			handlers.onStage1?.(event as unknown as PaintStage1Event);
		} else if (event.event === 'score') {
			handlers.onScore?.(event as unknown as PaintScoreEvent);
		} else if (event.event === 'attempt') {
			handlers.onAttempt?.(event as unknown as PaintAttemptEvent);
		} else if (event.event === 'error') {
			throw new Error(handlers.describeError(event.detail, Number(event.status ?? 500)));
		} else if (event.event === 'done') {
			done = event as unknown as T;
		}
	};

	for (;;) {
		let chunk: ReadableStreamReadResult<Uint8Array>;
		try {
			chunk = await reader.read();
		} catch (cause) {
			// A stopped request is the caller's; anything else cut the stream short.
			if (isAbort(cause)) throw cause;
			throw new ConnectionFailure('cut', cause instanceof Error ? cause.message : String(cause), { cause });
		}
		if (chunk.value) buffer += decoder.decode(chunk.value, { stream: true });
		// TextDecoder can retain an incomplete multibyte sequence. Flush it before
		// consuming the final unterminated NDJSON record at EOF.
		if (chunk.done) buffer += decoder.decode();
		let newline = buffer.indexOf('\n');
		while (newline >= 0) {
			const line = buffer.slice(0, newline).trim();
			buffer = buffer.slice(newline + 1);
			newline = buffer.indexOf('\n');
			consumeLine(line);
		}
		if (chunk.done) {
			consumeLine(buffer.trim());
			break;
		}
	}
	// The Server writes `error` when a run fails, so a stream that just ends was cut.
	if (!done) throw new ConnectionFailure('cut', 'paint stream ended before completion');
	return done;
}

/**
 * The four moments the indicator can be in: the request has left, and then one
 * per event the stream writes before the drawing exists.
 */
export type PaintStageMoment = 'requested' | 'sketch' | 'stage1' | 'score';

/**
 * The one function that picks the running indicator's words.
 *
 * `requested` is the only moment that has to be guessed, and the guess is now
 * a small one: the page knows whether it asked for Stage 0.5, so it names that
 * layer rather than the one after it.
 */
export function paintStageLabel(
	moment: PaintStageMoment,
	strings: LangPack,
	options: { sketchOn: boolean }
): string {
	if (moment === 'requested') {
		return options.sketchOn ? strings.stageSketching : strings.stageInterpreting;
	}
	if (moment === 'sketch') return strings.stageInterpreting;
	if (moment === 'stage1') return strings.stageStructuring('');
	return strings.stagePerforming;
}

/**
 * The stage name while a model call runs. The composition reading has no
 * layer event of its own -- it runs after Stage 1 and before the DDL is
 * committed -- so it used to wait under the label of the layer before it
 * (`解釈中…` in the stream, `DDL生成` for a single draw). The running call's
 * action names it; every other call keeps the label the run already shows
 * (2026-10-13). The laws stage, between the composition and the commit, names
 * itself the same way, and so does the color stage after it (2026-10-20).
 */
export function runningStageLabel(
	label: string,
	attempt: ProviderAttemptCount | null | undefined,
	strings: LangPack
): string {
	if (attempt?.action === 'select_image_catalog') return strings.imageSelectingCatalog;
	if (attempt?.action === 'write_image_ddl') return attempt.asked_again ? strings.imageRevisingDdl : strings.imageWritingDdl;
	if (attempt?.action === 'review_image_ddl') return attempt.asked_again ? strings.imageRevisingDdl : strings.imageReviewingDdl;
	if (attempt?.action === 'read_composition') return strings.stageReadingComposition;
	if (attempt?.action === 'choose_colors') return strings.stageChoosingColors;
	return attempt?.action === 'choose_laws' ? strings.stageChoosingLaws : label;
}

/**
 * What the indicator says about the model call it waits on. A first attempt
 * is a wait; later ones retry communication or ask again after a refused
 * completion proposal.
 */
export function providerAttemptText(
	attempt: ProviderAttemptCount | null | undefined,
	strings: LangPack
): string {
	if (!attempt) return '';
	if (attempt.asked_again === true) return strings.runStatusAskingAgain(attempt.attempt, attempt.max_attempts);
	return attempt.attempt > 1
		? strings.runStatusRetrying(attempt.attempt, attempt.max_attempts)
		: strings.runStatusAwaitingReply(attempt.attempt, attempt.max_attempts);
}

/**
 * Build the stream handlers that move the indicator. The page adds its own
 * bookkeeping through `onStage1`; everything that decides *what is shown* stays
 * here, where a test can watch all three switches at once.
 */
export function paintStageHandlers(
	strings: LangPack,
	setLabel: (label: string) => void,
	options: { sketchOn: boolean; onStage1?: (event: PaintStage1Event) => void }
): Pick<PaintStreamHandlers, 'onSketch' | 'onStage1' | 'onScore'> {
	return {
		onSketch: () => setLabel(paintStageLabel('sketch', strings, options)),
		onStage1: (event) => {
			setLabel(paintStageLabel('stage1', strings, options));
			options.onStage1?.(event);
		},
		onScore: () => setLabel(paintStageLabel('score', strings, options))
	};
}
