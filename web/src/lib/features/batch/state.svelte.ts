import type { ApiFetch } from '../../transport/api-fetch.ts';
import { isConnectionFailure, ConnectionFailure } from '../../transport/connection-failure.ts';
import type { PaintOptions, PaintResult } from '../run/current-work.ts';
import type { BatchFailure, BatchFailureReport } from './failure-report.svelte.ts';
import { startBatchLease, type BatchLeaseRecord } from './lease.ts';
import { dismissBatchRun, isBatchRunDismissed } from './dismissed-runs.ts';
import { dropFailedLine, planRetryRound } from './retry.ts';
import {
	batchStoppedPartWay,
	conditionsOfWork,
	latestBatchWork,
	linesToResume,
	numberedBatchLines,
	type BatchRunConditions,
	type BatchWork,
	type NumberedLine,
} from './resume.ts';

// These limits match the server history boundary. Both reads and writes are
// truncated there, so changing only the client does not expand the picker.
export const BATCH_PROMPT_HISTORY_LIMIT = 50;
export const BATCH_PROMPT_HISTORY_MAX_TEXT = 20_000;

// Resume discovery asks two questions at different depths. Offering resume
// needs only the newest numbered work; finding every missing line is deferred
// to the paged scan after the author selects it.
const BATCH_RESUME_PROBE_LIMIT = 20;
const BATCH_RESUME_SCAN_PAGE = 100;

// A line whose connection was cut (a restart of the Server, 2026-10-21) waits
// for the Server and is sent again, not counted as a failure: every 2s for the
// first 30s, then every 5s, for 5 minutes. A Server still away then interrupts
// the batch, which resumes from that line. A line cut three times in a row while
// the Server answers is a failure, so a cut that keeps coming cannot loop.
export type BatchServerWait = { limitMs: number; firstPhaseMs: number; firstIntervalMs: number; laterIntervalMs: number };
const BATCH_SERVER_WAIT: BatchServerWait = { limitMs: 300_000, firstPhaseMs: 30_000, firstIntervalMs: 2_000, laterIntervalMs: 5_000 };
const BATCH_CUTS_PER_LINE = 3;

function abortableDelay(ms: number, signal: AbortSignal): Promise<void> {
	return new Promise((resolve) => {
		if (signal.aborted) {
			resolve();
			return;
		}
		const done = () => {
			clearTimeout(timer);
			signal.removeEventListener('abort', done);
			resolve();
		};
		const timer = setTimeout(done, ms);
		signal.addEventListener('abort', done, { once: true });
	});
}

export type BatchLineResult = Pick<PaintResult,
	| 'sketch_text'
	| 'sketch_grain'
	| 'tokens_in_stage1'
	| 'tokens_in_stage2'
	| 'tokens_out_stage1'
	| 'tokens_out_stage2'
> & {
	ddl: string;
	thinking: string | null;
};

export type BatchResumeCandidate<TWork extends BatchWork = BatchWork> = {
	prompt: string;
	lines: NumberedLine[];
	runId: string | null;
	/** In-session pauses have their conditions before history has caught up. */
	work: TWork | null;
	conditions: BatchRunConditions;
	pending: NumberedLine[] | null;
	source: 'history' | 'session';
	reason?: 'failed';
	failureCount?: number;
};

type InterruptedBatchSnapshot<TWork extends BatchWork> = {
	prompt: string;
	lines: NumberedLine[];
	pending: NumberedLine[];
	completed: NumberedLine[];
	runId: string;
	conditions: BatchRunConditions;
	lastWork: TWork | null;
};

export type BatchStateDependencies = {
	apiFetch: ApiFetch;
	signedIn: () => boolean;
	paintable: (text: string) => boolean;
	setFailureReport: (report: BatchFailureReport | null) => void;
	getFailureReport?: () => BatchFailureReport | null;
	retryUnavailableMessage?: () => string;
	describeApiError?: (detail: unknown, status: number) => string;
	createRunId?: () => string;
	warn?: (message: string, cause: unknown) => void;
	/** The wait for the Server after a cut connection, and its clock; tests shorten them. */
	serverWait?: BatchServerWait;
	sleep?: (ms: number, signal: AbortSignal) => Promise<void>;
	now?: () => number;
};

export type BatchRunOptions<TResult extends BatchLineResult> = {
	resumeLines?: NumberedLine[];
	retryFailedLines?: NumberedLine[];
	/** Captured when a fresh run starts, then reapplied by every in-session resume. */
	runConditions?: BatchRunConditions;
	canvasAspectId: PaintOptions['canvasAspectId'];
	renderOverrides?: PaintOptions['renderOverrides'];
	maxRetries: number;
	paintLine: (text: string, options: PaintOptions) => Promise<TResult>;
	onLatestResult: (result: TResult, prompt: string) => void;
	onPaintComplete?: () => void;
	refreshAfterServerSave: () => Promise<void>;
	refreshAfterRun: () => Promise<void>;
};

export type ResumeInterruptedOptions = {
	blocked: () => boolean;
	applyConditions: (conditions: BatchRunConditions) => void | Promise<void>;
	run: (lines: NumberedLine[]) => Promise<void>;
};

function defaultRunId(): string {
	return typeof crypto?.randomUUID === 'function' ? crypto.randomUUID() : `${Date.now()}`;
}

/**
 * Route-instance owner for one batch prompt and its asynchronous lifecycle.
 *
 * The route lends this owner one-work painting and focused history callbacks;
 * it does not lend the history, settings, or Canvas controllers themselves.
 * A private run identity protects every reactive write, so an aborted request
 * that resolves late cannot repaint the current batch or its Canvas projection.
 */
export class BatchState<TResult extends BatchLineResult = BatchLineResult, TWork extends BatchWork = BatchWork> {
	input = $state('');
	promptHistory = $state<string[]>([]);
	resume = $state<BatchResumeCandidate<TWork> | null>(null);
	running = $state(false);
	startedAt = $state(0);
	workStartedAt = $state<number | null>(null);
	averageWorkMs = $state<number | null>(null);
	private workDurationTotal = 0;
	private workDurationCount = 0;
	/** Original plan size; current/total continue to describe the active retry round. */
	summaryTotal = $state(0);
	interrupted = $state(false);
	current = $state(0);
	total = $state(0);
	get summaryCurrent(): number {
		return this.current > 0 ? this.summaryTotal - this.total + this.current : 0;
	}
	retryRound = $state(0);
	success = $state(0);
	failures = $state<BatchFailure[]>([]);
	activeLine = $state<number | null>(null);
	// The observer identifies the line whose result has returned. It must not use
	// activeLine, which moves ahead while the previous line is still displayed.
	observedLine = $state<number | null>(null);
	activeDdl = $state<string | null>(null);
	// Batch prose is display-only and must not overwrite the editable single-work
	// sketch draft. It settles together with the observer DDL for one work.
	sketchText = $state<string | null>(null);
	sketchGrain = $state<unknown>(null);
	activeTokensIn = $state<number | null>(null);
	activeTokensOut = $state<number | null>(null);
	tokensInTotal = $state(0);
	tokensOutTotal = $state(0);
	latestResult = $state<TResult | null>(null);
	latestDdl = $state<string | null>(null);
	latestThinking = $state<string | null>(null);
	latestPrompt = $state('');
	autoFollowLatest = $state(false);
	/** The line waiting for the Server to answer again after its connection was cut. */
	waitingForServer = $state<number | null>(null);
	/** The batch stopped because the Server did not come back within the wait. */
	serverLost = $state(false);

	private readonly deps: BatchStateDependencies;
	private runIdentity = 0;
	private resumeDiscovery = 0;
	private stopRequested = false;
	private abortController: AbortController | null = null;
	private interruptedSnapshot: InterruptedBatchSnapshot<TWork> | null = null;
	private lastSnapshot: InterruptedBatchSnapshot<TWork> | null = null;
	resuming = $state(false);

	constructor(deps: BatchStateDependencies) {
		this.deps = deps;
	}

	get lines(): string[] {
		return this.input.split('\n');
	}

	get lineNumbersText(): string {
		return this.lines.map((_, index) => String(index + 1)).join('\n');
	}

	get nonEmpty(): number {
		return numberedBatchLines(this.input, this.deps.paintable).length;
	}

	get runningLineText(): string {
		return this.activeLine === null ? '' : (this.lines[this.activeLine - 1] ?? '').trim();
	}

	get canResume(): boolean {
		const candidate = this.resume;
		const report = this.deps.getFailureReport?.();
		return candidate !== null && !(candidate.reason === 'failed' && candidate.runId !== null
			&& report?.retry?.runId === candidate.runId && report.failures.length > 0);
	}

	get canRetryFailures(): boolean {
		return !this.running && (this.failures.length > 0 ||
			(this.deps.getFailureReport?.()?.failures.length ?? 0) > 0);
	}

	/** Enough progress for the button to explain an in-session continuation. */
	get resumeInfo(): { nextLine: number | null; pending: number | null; total: number; reason?: 'failed'; failureCount?: number } {
		const candidate = this.resume;
		if (!candidate) return { nextLine: null, pending: null, total: 0 };
		return {
			nextLine: candidate.pending?.[0]?.line ?? null,
			pending: candidate.pending?.length ?? null,
			total: candidate.lines.length,
			...(candidate.reason === 'failed' ? { reason: 'failed' as const, failureCount: candidate.failureCount } : {}),
		};
	}

	startFollowingLatest(): void {
		this.autoFollowLatest = true;
	}

	stopFollowingLatest(): void {
		this.autoFollowLatest = false;
	}

	clearPromptHistory(): void {
		this.resumeDiscovery += 1;
		this.promptHistory = [];
		this.resume = null;
		this.interruptedSnapshot = null;
		this.lastSnapshot = null;
		this.failures = [];
	}

	clearInput(): void {
		dismissBatchRun(this.resume?.runId ?? this.interruptedSnapshot?.runId);
		this.resumeDiscovery += 1;
		this.resume = null;
		this.interrupted = false;
		this.interruptedSnapshot = null;
		this.input = '';
		this.failures = [];
		this.lastSnapshot = null;
		this.activeLine = null;
		this.observedLine = null;
		this.activeDdl = null;
		this.latestPrompt = '';
		this.deps.setFailureReport(null);
	}

	async loadPromptHistory(): Promise<void> {
		if (!this.deps.signedIn()) {
			this.clearPromptHistory();
			return;
		}
		try {
			const response = await this.deps.apiFetch('/api/auth/me/batch-prompt-history', { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const data = await response.json() as { items?: unknown };
			this.promptHistory = Array.isArray(data.items)
				? this.normalizePromptHistory(data.items.filter((item): item is string => typeof item === 'string'))
				: [];
		} catch (cause) {
			this.promptHistory = [];
			this.warn('failed to load batch prompt history', cause);
		}
	}

	async rememberPrompt(prompt: string): Promise<void> {
		if (!this.deps.signedIn()) return;
		const previous = this.promptHistory;
		const next = this.normalizePromptHistory([prompt, ...this.promptHistory]);
		if (next.length === previous.length && next.every((item, index) => item === previous[index])) return;
		this.promptHistory = next;
		try {
			const response = await this.deps.apiFetch('/api/auth/me/batch-prompt-history', {
				method: 'PUT',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({ items: next }),
			});
			if (!response.ok) {
				const data = await response.json().catch(() => ({})) as { detail?: unknown };
				throw new Error(this.deps.describeApiError?.(data.detail, response.status) ?? `HTTP ${response.status}`);
			}
			const data = await response.json() as { items?: unknown };
			if (Array.isArray(data.items)) {
				this.promptHistory = this.normalizePromptHistory(
					data.items.filter((item): item is string => typeof item === 'string'),
				);
			}
		} catch (cause) {
			this.promptHistory = previous;
			this.warn('failed to update batch prompt history', cause);
		}
	}

	/** Ask the shallow listing only whether the newest batch stopped early. */
	async refreshResume(shared?: Promise<Response>): Promise<void> {
		const discovery = ++this.resumeDiscovery;
		if (this.resuming) return;
		if (this.deps.signedIn()) {
			try {
				const response = shared ? (await shared).clone() : await this.deps.apiFetch('/api/pipeline/batches', { cache: 'no-store' });
				if (response.status !== 404) {
					if (!response.ok) throw new Error(`HTTP ${response.status}`);
					const data = await response.json() as { batches?: BatchLeaseRecord[] };
					if (Array.isArray(data.batches)) {
						if (this.resumeDiscovery !== discovery || this.resuming) return;
						if (this.interruptedSnapshot) {
							const own = data.batches.find((item) => item.run_id === this.interruptedSnapshot?.runId);
							this.resume = own && (own.state === 'interrupted' || own.state === 'lease_expired' || own.state === 'stopped')
								? this.sessionResumeCandidate(this.interruptedSnapshot) : null;
							return;
						}
						const record = data.batches.find((item) => item.kind === 'web');
						if (record) {
							const lines = numberedBatchLines(record.prompt, this.deps.paintable);
							this.resume = !isBatchRunDismissed(record.run_id) && (record.state === 'interrupted' || record.state === 'lease_expired' || record.state === 'finished_with_failures') && lines.length === record.total
								? { prompt: record.prompt, lines, runId: record.run_id, work: null,
									conditions: record.conditions, pending: null, source: 'history',
									...(record.state === 'finished_with_failures' ? { reason: 'failed' as const, failureCount: record.total - record.completed } : {}) }
								: null;
							return;
						}
					}
				}
			} catch (cause) {
				// An unreadable lease is not evidence that a run has stopped.
				this.resume = null;
				this.warn('failed to check the batch lease', cause);
				return;
			}
		}
		if (this.interruptedSnapshot) {
			this.resume = this.sessionResumeCandidate(this.interruptedSnapshot);
			return;
		}
		const prompt = this.promptHistory[0] ?? '';
		if (!this.deps.signedIn() || !prompt) {
			if (this.resumeDiscovery === discovery) this.resume = null;
			return;
		}
		const lines = numberedBatchLines(prompt, this.deps.paintable);
		if (lines.length === 0) {
			if (this.resumeDiscovery === discovery) this.resume = null;
			return;
		}
		try {
			const work = latestBatchWork(await this.fetchWorksPage(0, BATCH_RESUME_PROBE_LIMIT)) as TWork | null;
			if (this.resumeDiscovery !== discovery || this.resuming || this.interruptedSnapshot) return;
			this.resume = work && !isBatchRunDismissed(work.batch_run_id) && batchStoppedPartWay(lines, work)
				? {
					prompt,
					lines,
					runId: work.batch_run_id ?? null,
					work,
					conditions: conditionsOfWork(work),
					pending: null,
					source: 'history',
				}
				: null;
		} catch (cause) {
			if (this.resumeDiscovery === discovery && !this.interruptedSnapshot) this.resume = null;
			this.warn('failed to check whether the last batch reached its end', cause);
		}
	}

	async resumeInterrupted(options: ResumeInterruptedOptions): Promise<void> {
		const candidate = this.resume;
		if (!candidate || options.blocked() || this.resuming || this.running) return;
		this.resuming = true;
		const selection = ++this.resumeDiscovery;
		try {
			let snapshot = this.interruptedSnapshot;
			if (!snapshot || candidate.source !== 'session') {
				// A reload has no client snapshot. Discover its already-saved lines
				// before starting anything; a failed lookup must never turn into a
				// full rerun.
				const works = await this.collectRunWorks(candidate.runId, candidate.lines.length);
				// Sign-out, a prompt reset, or another resume discovery can happen
				// while this paged lookup is waiting. None may apply this stale
				// candidate's settings or restart its work.
				if (this.resumeDiscovery !== selection || options.blocked() || this.resume !== candidate) return;
				const remaining = linesToResume(candidate.lines, works, candidate.runId);
				if (remaining.length === 0) {
					this.resume = null;
					return;
				}
				snapshot = {
					prompt: candidate.prompt,
					lines: candidate.lines,
					pending: remaining,
					completed: candidate.lines.filter((line) => !remaining.some((item) => item.line === line.line)),
					runId: candidate.runId ?? (this.deps.createRunId ?? defaultRunId)(),
					conditions: candidate.conditions,
					lastWork: candidate.work,
				};
				this.interruptedSnapshot = snapshot;
			}
			if (snapshot.pending.length === 0) {
				this.resume = null;
				return;
			}
			await options.applyConditions(snapshot.conditions);
			// Refill the whole prompt: the pending plan keeps the original numbers.
			this.input = snapshot.prompt;
			this.resume = null;
			const run = options.run(snapshot.pending);
			await run;
		} finally {
			this.resuming = false;
			if (this.interruptedSnapshot) await this.refreshResume();
		}
	}

	async retryFailed(options: ResumeInterruptedOptions): Promise<void> {
		if (!this.canRetryFailures || options.blocked() || this.resuming) return;
		const report = this.deps.getFailureReport?.();
		const restoreConditions = this.lastSnapshot !== null || report?.retry !== undefined || this.resume !== null;
		let snapshot = this.lastSnapshot;
		let failures = this.failures;
		if (!snapshot || failures.length === 0) {
			if (!report?.failures.length) return;
			const context = report.retry;
			const prompt = context?.prompt ?? this.promptHistory[0] ?? '';
			const lines = numberedBatchLines(prompt, this.deps.paintable);
			const failedNumbers = context?.failedLines ?? report.failures.map((failure) => failure.line);
			const selected = lines.filter((line) => failedNumbers.includes(line.line));
			// Legacy reports may truncate the displayed input. Recover it only
			// from a matching original prompt, never by painting the excerpt.
			if (selected.length === 0 || selected.length !== new Set(failedNumbers).size ||
				(!context && report.failures.some((failure) =>
					!selected.some((line) => line.line === failure.line && line.input === failure.input)))) {
				throw new Error(this.deps.retryUnavailableMessage?.() ?? 'Original batch descriptions are unavailable for retry.');
			}
			const pending = context ? lines.filter((line) => context.pendingLines.includes(line.line)) : selected;
			snapshot = {
				prompt, lines, pending,
				completed: lines.filter((line) => !pending.some((item) => item.line === line.line)),
				runId: context?.runId ?? this.resume?.runId ?? (this.deps.createRunId ?? defaultRunId)(),
				conditions: context?.conditions ?? this.resume?.conditions ?? this.emptyConditions(),
				lastWork: this.resume?.work ?? null,
			};
			failures = selected.map((line) => ({ ...line,
				message: report.failures.find((failure) => failure.line === line.line)?.message ?? '' }));
		}
		this.resuming = true;
		try {
			this.lastSnapshot = snapshot;
			this.failures = failures;
			this.input = snapshot.prompt;
			if (restoreConditions) {
				await options.applyConditions(snapshot.conditions);
			}
			await options.run(failures.map(({ line, input }) => ({ line, input })));
		} finally {
			this.resuming = false;
		}
	}

	async run(options: BatchRunOptions<TResult>): Promise<void> {
		if (this.running) return;
		const retrying = options.retryFailedLines !== undefined;
		const previousFailures = retrying ? this.failures : [];
		const resumingSnapshot = retrying ? this.lastSnapshot : options.resumeLines ? this.interruptedSnapshot : null;
		if (!resumingSnapshot) {
			this.resumeDiscovery += 1;
			this.resume = null;
		}
		const identity = ++this.runIdentity;
		const abortController = new AbortController();
		this.abortController = abortController;
		this.stopRequested = false;
		this.running = true;
		this.startedAt = Date.now();
		// A caller may need asynchronous lineage work before it invokes this
		// owner. Keep the selection guarded until this run has claimed `running`.
		if (resumingSnapshot) this.resuming = false;
		this.resetForRun();
		if (retrying) this.failures = previousFailures;

		const lines = numberedBatchLines(this.input, this.deps.paintable);
		const paintLines = options.retryFailedLines ?? options.resumeLines ?? lines;
		const lineTotal = paintLines.length;
		const snapshot = resumingSnapshot ?? {
			prompt: this.input,
			lines,
			pending: [...paintLines],
			completed: [],
			runId: (this.deps.createRunId ?? defaultRunId)(),
			conditions: options.runConditions ?? this.emptyConditions(),
			lastWork: null,
		};
		this.interruptedSnapshot = snapshot;
		this.lastSnapshot = snapshot;
		this.summaryTotal = snapshot.lines.length;
		const batchRunId = snapshot.runId;
		this.total = lineTotal;
		let interrupted = false;
		let finishedAllLines = false;
		let lease: Awaited<ReturnType<typeof startBatchLease>> = null;

		const isCurrent = (): boolean => (
			this.runIdentity === identity
			&& this.abortController === abortController
			&& !this.stopRequested
			&& !abortController.signal.aborted
		);

		/** true = painted, string = failure message, null = interrupted or stale. */
		const paintBatchLine = async (item: NumberedLine): Promise<true | string | null> => {
			this.workStartedAt = null;
			// A connection a restart of the Server cut is not the line's failure: wait
			// for the Server, and send the line again unless it was saved before the cut.
			for (let cuts = 1; ; cuts += 1) {
				const outcome = await paintBatchAttempt(item);
				if (!isConnectionFailure(outcome)) return outcome;
				if (cuts >= BATCH_CUTS_PER_LINE) return outcome.message;
				const back = await this.waitForServer(item.line, isCurrent, abortController.signal);
				if (back === null) return null;
				if (!back) {
					this.serverLost = true;
					return null;
				}
				const settled = await this.waitForBatchToSettle(batchRunId, isCurrent, abortController.signal);
				if (!settled) {
					this.serverLost = true;
					return null;
				}
				let savedWork: TWork | null;
				try {
					savedWork = await this.savedLineWork(batchRunId, item.line);
				} catch (cause) {
					this.warn('failed to check whether a cut batch line was saved', cause);
					return outcome.message;
				}
				if (!isCurrent()) return null;
				if (savedWork) {
					this.markSnapshotCompleted(snapshot, item);
					this.success += 1;
					this.recordWorkDuration(savedWork.at);
					try {
						await options.refreshAfterServerSave();
					} catch (cause) {
						this.warn('failed to refresh history after saved batch work', cause);
					}
					return isCurrent() ? true : null;
				}
			}
		};

		/** One send of a line; a cut connection comes back as its failure for the caller to wait on. */
		const paintBatchAttempt = async (item: NumberedLine): Promise<true | string | null | ConnectionFailure> => {
			if (!isCurrent()) return null;
			this.activeLine = item.line;
			let saved = false;
			try {
				if (lease) {
					try { await lease.refresh(); }
					catch (cause) {
						if (abortController.signal.aborted) return null;
						return new ConnectionFailure('unreachable', cause instanceof Error ? cause.message : String(cause), { cause });
					}
				}
				if (this.workStartedAt === null) this.workStartedAt = (this.deps.now ?? Date.now)();
				const painted = await options.paintLine(item.input, {
					historyInput: `#${item.line} ${item.input}`,
					sourceText: item.input,
					displayLabel: `#${item.line}`,
					batchLineNumber: item.line,
					batchRunId,
					batchLease: lease?.lease,
					canvasAspectId: options.canvasAspectId,
					renderOverrides: options.renderOverrides,
					signal: abortController.signal,
				});
				if (!isCurrent()) return null;
				saved = true;
				this.markSnapshotCompleted(snapshot, item);
				this.success += 1;
				this.recordWorkDuration();

				// These observer quantities settle together and always describe one work.
				this.observedLine = item.line;
				this.activeDdl = painted.ddl;
				this.sketchText = painted.sketch_text ?? null;
				this.sketchGrain = painted.sketch_grain ?? null;
				this.activeTokensIn = (painted.tokens_in_stage1 ?? 0) + (painted.tokens_in_stage2 ?? 0) || null;
				this.activeTokensOut = (painted.tokens_out_stage1 ?? 0) + (painted.tokens_out_stage2 ?? 0) || null;
				this.tokensInTotal += this.activeTokensIn ?? 0;
				this.tokensOutTotal += this.activeTokensOut ?? 0;
				this.latestResult = painted;
				this.latestDdl = painted.ddl;
				this.latestThinking = painted.thinking;
				this.latestPrompt = `#${item.line} ${item.input}`;
				await options.refreshAfterServerSave();
				if (!isCurrent()) return null;
				options.onLatestResult(painted, this.latestPrompt);
				return true;
			} catch (cause) {
				// Saving the work and refreshing its history are separate operations.
				// Do not repaint a work merely because the ancillary refresh failed.
				if (saved) {
					this.warn('failed to refresh history after saved batch work', cause);
					return true;
				}
				if (!isCurrent()) return null;
				if (isConnectionFailure(cause)) return cause;
				return cause instanceof Error ? cause.message : String(cause);
			}
		};

		const publishFailureReport = () => {
			// Progress is repointed at each retry round; reports retain the run total.
			this.deps.setFailureReport(
				this.failures.length > 0
					? { success: retrying ? snapshot.completed.length : this.success,
						total: retrying ? snapshot.lines.length : lineTotal, failures: this.failures,
						retry: { prompt: snapshot.prompt, runId: snapshot.runId, conditions: snapshot.conditions,
							failedLines: this.failures.map((failure) => failure.line),
							pendingLines: snapshot.pending.map((line) => line.line) } }
					: null,
			);
		};

		try {
			lease = await startBatchLease(this.deps.apiFetch, batchRunId, snapshot.prompt, snapshot.conditions,
				snapshot.lines.length, () => snapshot.completed.length, () => {
					this.stopRequested = true;
					this.interrupted = true;
					abortController.abort();
				});
			for (let index = 0; index < paintLines.length; index += 1) {
				if (!isCurrent()) { interrupted = true; this.interrupted = true; break; }
				this.current = index + 1;
				const outcome = await paintBatchLine(paintLines[index]);
				if (outcome === null) { interrupted = true; this.interrupted = true; break; }
				if (outcome !== true) {
					this.failures = [
						...dropFailedLine(this.failures, paintLines[index].line),
						{ line: paintLines[index].line, input: paintLines[index].input, message: outcome },
					];
				} else if (retrying) {
					this.failures = dropFailedLine(this.failures, paintLines[index].line);
				}
				publishFailureReport();
			}

			// Retry failed lines only. An interrupted run deliberately skips retries.
			let completedRetryRounds = 0;
			for (;;) {
				const round = planRetryRound(
					this.failures,
					completedRetryRounds,
					options.maxRetries,
					interrupted || !isCurrent(),
				);
				if (!round) break;
				this.retryRound = round.round;
				this.total = round.items.length;
				for (let index = 0; index < round.items.length; index += 1) {
					if (!isCurrent()) { interrupted = true; this.interrupted = true; break; }
					this.current = index + 1;
					const item = round.items[index];
					const outcome = await paintBatchLine(item);
					if (outcome === null) { interrupted = true; this.interrupted = true; break; }
					if (outcome === true) {
						this.failures = dropFailedLine(this.failures, item.line);
					} else {
						this.failures = this.failures.map((failure) =>
							failure.line === item.line ? { ...failure, message: outcome } : failure,
						);
					}
					publishFailureReport();
				}
				if (interrupted) break;
				completedRetryRounds += 1;
			}

			finishedAllLines = !interrupted && isCurrent();
			this.retryRound = 0;
			this.total = lineTotal;
			options.onPaintComplete?.();
			try {
				await options.refreshAfterRun();
			} catch (cause) {
				// The completed work and the local interruption snapshot are already
				// authoritative here. A history refresh must not hide Resume.
				this.warn('failed to refresh history after batch run', cause);
			}
			publishFailureReport();
			if (!interrupted && isCurrent() && !(retrying && snapshot.pending.some((line) =>
				!paintLines.some((item) => item.line === line.line)))) this.interruptedSnapshot = null;
			await this.refreshResume();
		} finally {
			if (lease) {
				const unfinishedBeforeRetry = retrying && snapshot.pending.some((line) =>
					!paintLines.some((item) => item.line === line.line));
				const state = this.serverLost || interrupted || unfinishedBeforeRetry || (!finishedAllLines && !this.stopRequested) ? 'interrupted'
					: this.stopRequested ? 'stopped' : snapshot.pending.length ? 'finished_with_failures' : 'completed';
				await lease.finish(state).catch((cause) => this.warn('failed to close the batch lease', cause));
			}
			if (this.abortController === abortController) {
				this.abortController = null;
				this.stopRequested = false;
				this.running = false;
				this.current = 0;
				this.retryRound = 0;
				this.activeLine = null;
				this.observedLine = null;
				this.activeDdl = null;
				this.activeTokensIn = null;
				this.activeTokensOut = null;
			}
			if (lease) await this.refreshResume();
		}
	}

	stop(): void {
		if (!this.running) return;
		this.stopRequested = true;
		this.interrupted = true;
		this.abortController?.abort();
	}

	private resetForRun(): void {
		this.workStartedAt = null;
		this.averageWorkMs = null;
		this.workDurationTotal = 0;
		this.workDurationCount = 0;
		this.current = 0;
		this.interrupted = false;
		this.total = 0;
		this.retryRound = 0;
		this.success = 0;
		this.failures = [];
		this.activeLine = null;
		this.observedLine = null;
		this.activeDdl = null;
		this.sketchText = null;
		this.sketchGrain = null;
		this.activeTokensIn = null;
		this.activeTokensOut = null;
		this.tokensInTotal = 0;
		this.tokensOutTotal = 0;
		this.latestResult = null;
		this.latestDdl = null;
		this.latestThinking = null;
		this.latestPrompt = '';
		this.autoFollowLatest = true;
		this.waitingForServer = null;
		this.serverLost = false;
		this.deps.setFailureReport(null);
	}

	private recordWorkDuration(savedAt?: number | null): void {
		if (this.workStartedAt === null) return;
		const now = (this.deps.now ?? Date.now)();
		// A recovered work can have been saved while the connection was down.
		// Use its timestamp only when it fits the client's observed interval.
		const ended = savedAt != null && savedAt >= this.workStartedAt && savedAt <= now ? savedAt : now;
		this.workDurationTotal += Math.max(0, ended - this.workStartedAt);
		this.workDurationCount += 1;
		this.averageWorkMs = this.workDurationTotal / this.workDurationCount;
	}

	private emptyConditions(): BatchRunConditions {
		return {
			stage1Model: null,
			stage2Model: null,
			catalogId: null,
			catalogMode: null,
			sketchGrain: null,
			wild: null,
			canvasAspectId: null,
			route: null,
			composition: null,
		};
	}

	private markSnapshotCompleted(snapshot: InterruptedBatchSnapshot<TWork>, item: NumberedLine): void {
		if (!snapshot.completed.some((line) => line.line === item.line)) {
			snapshot.completed = [...snapshot.completed, item];
		}
		snapshot.pending = snapshot.pending.filter((line) => line.line !== item.line);
	}

	private sessionResumeCandidate(snapshot: InterruptedBatchSnapshot<TWork>): BatchResumeCandidate<TWork> | null {
		if (snapshot.pending.length === 0) return null;
		return {
			prompt: snapshot.prompt,
			lines: snapshot.lines,
			runId: snapshot.runId,
			work: snapshot.lastWork,
			conditions: snapshot.conditions,
			pending: snapshot.pending,
			source: 'session',
		};
	}

	private normalizePromptHistory(items: string[]): string[] {
		const normalized: string[] = [];
		const seen = new Set<string>();
		for (const item of items) {
			const prompt = item.trim().replace(/\r\n/g, '\n').replace(/\r/g, '\n');
			if (!prompt || seen.has(prompt) || prompt.length > BATCH_PROMPT_HISTORY_MAX_TEXT) continue;
			normalized.push(prompt);
			seen.add(prompt);
			if (normalized.length >= BATCH_PROMPT_HISTORY_LIMIT) break;
		}
		return normalized;
	}

	private async fetchWorksPage(offset: number, limit: number, runId: string | null = null): Promise<TWork[]> {
		const params = new URLSearchParams({
			offset: String(offset),
			limit: String(limit),
			include_svg: 'false',
		});
		if (runId !== null) params.set('batch_run_id', runId);
		const response = await this.deps.apiFetch(`/api/history?${params.toString()}`, { cache: 'no-store' });
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		const data = await response.json() as { items?: TWork[] };
		if (!Array.isArray(data.items)) throw new Error('History response is invalid');
		return data.items;
	}

	/**
	 * Wait for the Server to answer again after a cut connection: true when it
	 * does, false when the wait runs out, null when the batch stopped meanwhile.
	 */
	private async waitForServer(line: number, isCurrent: () => boolean, signal: AbortSignal): Promise<boolean | null> {
		const wait = this.deps.serverWait ?? BATCH_SERVER_WAIT;
		const sleep = this.deps.sleep ?? abortableDelay;
		const now = this.deps.now ?? Date.now;
		const started = now();
		if (!isCurrent()) return null;
		this.waitingForServer = line;
		try {
			for (;;) {
				const answers = await this.serverAnswers(signal);
				if (!isCurrent()) return null;
				if (answers) return true;
				const waited = now() - started;
				if (waited >= wait.limitMs) return false;
				await sleep(waited < wait.firstPhaseMs ? wait.firstIntervalMs : wait.laterIntervalMs, signal);
				if (!isCurrent()) return null;
			}
		} finally {
			if (this.waitingForServer === line) this.waitingForServer = null;
		}
	}

	private async serverAnswers(signal: AbortSignal): Promise<boolean> {
		try {
			const response = await this.deps.apiFetch('/api/info', { cache: 'no-store', signal });
			return response.ok;
		} catch {
			return false;
		}
	}

	/** Do not repeat a cut request while the server is still finishing its work. */
	private async waitForBatchToSettle(runId: string, isCurrent: () => boolean, signal: AbortSignal): Promise<boolean> {
		const wait = this.deps.serverWait ?? BATCH_SERVER_WAIT;
		const sleep = this.deps.sleep ?? abortableDelay;
		const now = this.deps.now ?? Date.now;
		const started = now();
		while (isCurrent()) {
			try {
				const response = await this.deps.apiFetch('/api/pipeline/activity', { cache: 'no-store', signal });
				if (response.status === 404) return true; // Older Server has only the historical recovery path.
				if (response.ok) {
					const body = await response.json() as { executions?: Array<{ batch_run_id?: string }> };
					if (Array.isArray(body.executions) && !body.executions.some((item) => item.batch_run_id === runId)) return true;
				}
			} catch { /* Recheck until the same bounded server wait ends. */ }
			if (now() - started >= wait.limitMs) return false;
			await sleep(wait.firstIntervalMs, signal);
		}
		return false;
	}

	/** The work a batch line saved, looked up among the newest works as resume does. */
	private async savedLineWork(runId: string, line: number): Promise<TWork | null> {
		const works = await this.collectRunWorks(runId, Number.POSITIVE_INFINITY);
		return works.find((work) => (work.batch_run_id ?? null) === runId && work.batch_line_number === line) ?? null;
	}

	/** Walk the listing until every needed work is found or the listing ends. */
	private async collectRunWorks(runId: string | null, need: number): Promise<TWork[]> {
		const collected: TWork[] = [];
		for (let offset = 0; ; offset += BATCH_RESUME_SCAN_PAGE) {
			const page = await this.fetchWorksPage(offset, BATCH_RESUME_SCAN_PAGE, runId);
			if (page.length === 0) break;
			const mine = page.filter((item) =>
				typeof item.batch_line_number === 'number'
				&& (runId === null || (item.batch_run_id ?? null) === runId));
			collected.push(...mine);
			if (collected.length >= need) break;
			if (page.length < BATCH_RESUME_SCAN_PAGE) break;
		}
		return collected;
	}

	private warn(message: string, cause: unknown): void {
		if (this.deps.warn) this.deps.warn(message, cause);
		else console.warn(message, cause);
	}
}
