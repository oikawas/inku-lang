import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { PaintOptions, PaintResult } from '../run/current-work.ts';
import type { BatchFailure, BatchFailureReport } from './failure-report.svelte.ts';
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
const BATCH_RESUME_SCAN_MAX = 500;

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
	describeApiError?: (detail: unknown, status: number) => string;
	createRunId?: () => string;
	warn?: (message: string, cause: unknown) => void;
};

export type BatchRunOptions<TResult extends BatchLineResult> = {
	resumeLines?: NumberedLine[];
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
	applyConditions: (conditions: BatchRunConditions) => void;
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
	interrupted = $state(false);
	current = $state(0);
	total = $state(0);
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

	private readonly deps: BatchStateDependencies;
	private runIdentity = 0;
	private resumeDiscovery = 0;
	private stopRequested = false;
	private abortController: AbortController | null = null;
	private interruptedSnapshot: InterruptedBatchSnapshot<TWork> | null = null;
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
		return this.resume !== null;
	}

	/** Enough progress for the button to explain an in-session continuation. */
	get resumeInfo(): { nextLine: number | null; pending: number | null; total: number } {
		const candidate = this.resume;
		if (!candidate) return { nextLine: null, pending: null, total: 0 };
		return {
			nextLine: candidate.pending?.[0]?.line ?? null,
			pending: candidate.pending?.length ?? null,
			total: candidate.lines.length,
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
	}

	clearInput(): void {
		this.input = '';
		this.failures = [];
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
	async refreshResume(): Promise<void> {
		const discovery = ++this.resumeDiscovery;
		if (this.resuming) return;
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
			this.resume = work && batchStoppedPartWay(lines, work)
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
			options.applyConditions(snapshot.conditions);
			// Refill the whole prompt: the pending plan keeps the original numbers.
			this.input = snapshot.prompt;
			this.resume = null;
			const run = options.run(snapshot.pending);
			await run;
		} finally {
			this.resuming = false;
			if (this.interruptedSnapshot) this.resume = this.sessionResumeCandidate(this.interruptedSnapshot);
		}
	}

	async run(options: BatchRunOptions<TResult>): Promise<void> {
		if (this.running) return;
		const resumingSnapshot = options.resumeLines ? this.interruptedSnapshot : null;
		if (!resumingSnapshot) {
			this.resumeDiscovery += 1;
			this.resume = null;
		}
		const identity = ++this.runIdentity;
		const abortController = new AbortController();
		this.abortController = abortController;
		this.stopRequested = false;
		this.running = true;
		// A caller may need asynchronous lineage work before it invokes this
		// owner. Keep the selection guarded until this run has claimed `running`.
		if (resumingSnapshot) this.resuming = false;
		this.resetForRun();

		const lines = numberedBatchLines(this.input, this.deps.paintable);
		const paintLines = options.resumeLines ?? lines;
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
		const batchRunId = snapshot.runId;
		this.total = lineTotal;
		let interrupted = false;

		const isCurrent = (): boolean => (
			this.runIdentity === identity
			&& this.abortController === abortController
			&& !this.stopRequested
			&& !abortController.signal.aborted
		);

		/** true = painted, string = failure message, null = interrupted or stale. */
		const paintBatchLine = async (item: NumberedLine): Promise<true | string | null> => {
			if (!isCurrent()) return null;
			this.activeLine = item.line;
			let saved = false;
			try {
				const painted = await options.paintLine(item.input, {
					historyInput: `#${item.line} ${item.input}`,
					sourceText: item.input,
					displayLabel: `#${item.line}`,
					batchLineNumber: item.line,
					batchRunId,
					canvasAspectId: options.canvasAspectId,
					renderOverrides: options.renderOverrides,
					signal: abortController.signal,
				});
				if (!isCurrent()) return null;
				saved = true;
				this.markSnapshotCompleted(snapshot, item);
				this.success += 1;

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
				options.onLatestResult(painted, this.latestPrompt);
				await options.refreshAfterServerSave();
				if (!isCurrent()) return null;
				return true;
			} catch (cause) {
				// Saving the work and refreshing its history are separate operations.
				// Do not repaint a work merely because the ancillary refresh failed.
				if (saved) {
					this.warn('failed to refresh history after saved batch work', cause);
					return true;
				}
				if (!isCurrent()) return null;
				return cause instanceof Error ? cause.message : String(cause);
			}
		};

		const publishFailureReport = () => {
			// Progress is repointed at each retry round; reports retain the run total.
			this.deps.setFailureReport(
				this.failures.length > 0
					? { success: this.success, total: lineTotal, failures: this.failures }
					: null,
			);
		};

		try {
			for (let index = 0; index < paintLines.length; index += 1) {
				if (!isCurrent()) { interrupted = true; this.interrupted = true; break; }
				this.current = index + 1;
				const outcome = await paintBatchLine(paintLines[index]);
				if (outcome === null) { interrupted = true; this.interrupted = true; break; }
				if (outcome !== true) {
					this.failures = [
						...this.failures,
						{ line: paintLines[index].line, input: paintLines[index].input, message: outcome },
					];
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
			if (!interrupted && isCurrent()) this.interruptedSnapshot = null;
			await this.refreshResume();
		} finally {
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
		}
	}

	stop(): void {
		if (!this.running) return;
		this.stopRequested = true;
		this.interrupted = true;
		this.abortController?.abort();
	}

	private resetForRun(): void {
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
		this.deps.setFailureReport(null);
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

	private async fetchWorksPage(offset: number, limit: number): Promise<TWork[]> {
		const params = new URLSearchParams({
			offset: String(offset),
			limit: String(limit),
			include_svg: 'false',
		});
		const response = await this.deps.apiFetch(`/api/history?${params.toString()}`, { cache: 'no-store' });
		if (!response.ok) throw new Error(`HTTP ${response.status}`);
		const data = await response.json() as { items?: TWork[] };
		return Array.isArray(data.items) ? data.items : [];
	}

	/** Walk backward only until this run has been passed or enough works exist. */
	private async collectRunWorks(runId: string | null, need: number): Promise<TWork[]> {
		const collected: TWork[] = [];
		for (let offset = 0; offset < BATCH_RESUME_SCAN_MAX; offset += BATCH_RESUME_SCAN_PAGE) {
			const page = await this.fetchWorksPage(offset, BATCH_RESUME_SCAN_PAGE);
			if (page.length === 0) break;
			const mine = page.filter((item) =>
				typeof item.batch_line_number === 'number'
				&& (runId === null || (item.batch_run_id ?? null) === runId));
			collected.push(...mine);
			// Works from one run are contiguous; newer unrelated works may precede it.
			if (mine.length === 0 && collected.length > 0) break;
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
