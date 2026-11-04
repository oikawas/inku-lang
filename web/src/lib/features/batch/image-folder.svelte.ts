import {
	folderNameOf,
	loadBatchSource,
	loadFolderHistory,
	pictureKey,
	picturesOfFolder,
	picturesToPaint,
	recordOf,
	relativePathOf,
	rememberFolder,
	saveBatchSource,
	saveFolderHistory,
	type BatchSource,
	type FolderFile,
	type ImageFolderFailure,
	type ImageFolderRecord,
} from './image-folder.ts';
import { dismissBatchRun, isBatchRunDismissed } from './dismissed-runs.ts';

export type ImageFolderRunOptions<TFile extends FolderFile> = {
	/** Start over: forget which pictures of this folder are done. */
	fromStart: boolean;
	batchRunId?: string;
	/** Paints and saves one picture; throws when it could not. */
	paintPicture: (file: TFile, signal: AbortSignal) => Promise<void>;
	/** A cut connection stops the run (resumable) instead of failing one picture. */
	stopsTheRun: (cause: unknown) => boolean;
	describe: (cause: unknown) => string;
};

export type ImageFolderStorage = {
	loadHistory: () => ImageFolderRecord[];
	saveHistory: (history: readonly ImageFolderRecord[]) => void;
	loadSource: () => BatchSource;
	saveSource: (source: BatchSource) => void;
};

const browserStorage: ImageFolderStorage = {
	loadHistory: () => loadFolderHistory(),
	saveHistory: (history) => saveFolderHistory(history),
	loadSource: () => loadBatchSource(),
	saveSource: (source) => saveBatchSource(source),
};

/**
 * The batch tab's picture side: the picked folder, its run, and the history
 * that lets a stopped run go on after the folder is picked again.
 */
export class ImageFolderBatch<TFile extends FolderFile = File> {
	source = $state<BatchSource>('text');
	history = $state<ImageFolderRecord[]>([]);
	pictures = $state<TFile[]>([]);
	folderName = $state('');
	running = $state(false);
	startedAt = $state(0);
	workStartedAt = $state<number | null>(null);
	averageWorkMs = $state<number | null>(null);
	/** The last run was stopped, by the author or by a lost connection. */
	interrupted = $state(false);
	current = $state(0);
	total = $state(0);
	summaryTotal = $state(0);
	get summaryCurrent(): number {
		return this.current > 0 ? this.summaryTotal - this.total + this.current : 0;
	}
	activePath = $state('');
	success = $state(0);
	/** Why the last run stopped by itself; null when the author stopped it or it ended. */
	stopReason = $state<string | null>(null);
	resumeBlocked = $state(false);

	private readonly store: ImageFolderStorage;
	private abortController: AbortController | null = null;
	private stopRequested = false;

	constructor(store: ImageFolderStorage = browserStorage) {
		this.store = store;
		this.source = store.loadSource();
		this.history = store.loadHistory();
	}

	setSource(source: BatchSource): void {
		if (this.running) return;
		this.source = source;
		this.store.saveSource(source);
	}

	clearInput(): void {
		if (this.running) return;
		dismissBatchRun(this.record?.batchRunId);
		this.pictures = [];
		this.folderName = '';
		this.interrupted = false;
		this.stopReason = null;
		this.resumeBlocked = false;
		this.success = 0;
	}

	/** The files of the folder the author picked, as the browser handed them over. */
	pick(files: readonly TFile[]): void {
		if (this.running) return;
		this.pictures = picturesOfFolder(files);
		this.folderName = folderNameOf(files);
		this.interrupted = false;
		this.stopReason = null;
		this.success = 0;
		this.resumeBlocked = !!this.record?.batchRunId;
	}

	get rawRecord(): ImageFolderRecord | null {
		return this.folderName ? recordOf(this.history, this.folderName) : null;
	}

	get record(): ImageFolderRecord | null {
		const record = this.rawRecord;
		return isBatchRunDismissed(record?.batchRunId) ? null : record;
	}

	get visibleHistory(): ImageFolderRecord[] {
		return this.history.filter((record) => !isBatchRunDismissed(record.batchRunId));
	}

	get pending(): TFile[] {
		return picturesToPaint(this.pictures, this.record);
	}

	/** Pictures of the picked folder already painted in an earlier run. */
	get doneCount(): number {
		return this.pictures.length - this.pending.length;
	}

	/** The failures of the last run that belong to the picked folder. */
	get failures(): ImageFolderFailure[] {
		return this.record?.failures ?? [];
	}

	markServerCompleted(lines: readonly number[]): void {
		const record = this.record;
		if (!record?.batchKeys) return;
		const done = new Set(record.done);
		for (const line of lines) if (record.batchKeys[line - 1]) done.add(record.batchKeys[line - 1]);
		this.history = rememberFolder(this.history, { ...record, done: [...done], updatedAt: Date.now() });
		this.store.saveHistory(this.history);
	}

	async run(options: ImageFolderRunOptions<TFile>): Promise<void> {
		if (this.running || this.pictures.length === 0) return;
		const name = this.folderName;
		let record: ImageFolderRecord = options.fromStart || !this.record
			? { name, total: this.pictures.length, done: [], failures: [], updatedAt: Date.now() }
			: { ...this.record, total: this.pictures.length, updatedAt: Date.now() };
		const queue = picturesToPaint(this.pictures, record);
		if (options.batchRunId) record = { ...record, batchRunId: options.batchRunId, batchKeys: queue.map(pictureKey) };
		const save = (next: ImageFolderRecord) => {
			record = next;
			this.history = rememberFolder(this.history, next);
			this.store.saveHistory(this.history);
		};
		save(record);
		if (queue.length === 0) return;

		const abortController = new AbortController();
		this.abortController = abortController;
		this.stopRequested = false;
		this.running = true;
		this.startedAt = Date.now();
		this.workStartedAt = null;
		this.averageWorkMs = null;
		let workDurationTotal = 0;
		let workDurationCount = 0;
		this.interrupted = false;
		this.stopReason = null;
		this.success = 0;
		this.current = 0;
		this.total = queue.length;
		this.summaryTotal = this.pictures.length;
		try {
			for (const [index, file] of queue.entries()) {
				if (this.stopRequested) break;
				const key = pictureKey(file);
				this.current = index + 1;
				this.activePath = relativePathOf(file);
				try {
					this.workStartedAt = Date.now();
					await options.paintPicture(file, abortController.signal);
					if (!abortController.signal.aborted) {
						workDurationTotal += Math.max(0, Date.now() - this.workStartedAt);
						this.averageWorkMs = workDurationTotal / ++workDurationCount;
					}
					this.success += 1;
					save({
						...record,
						done: [...record.done, key],
						failures: record.failures.filter((item) => item.key !== key),
						updatedAt: Date.now(),
					});
				} catch (cause) {
					if (this.stopRequested || abortController.signal.aborted) break;
					if (options.stopsTheRun(cause)) {
						this.stopReason = options.describe(cause);
						this.stopRequested = true;
						break;
					}
					save({
						...record,
						failures: [
							...record.failures.filter((item) => item.key !== key),
							{ key, path: relativePathOf(file), message: options.describe(cause) },
						],
						updatedAt: Date.now(),
					});
				}
			}
		} finally {
			this.interrupted = this.stopRequested && picturesToPaint(this.pictures, record).length > 0;
			this.running = false;
			this.activePath = '';
			if (this.abortController === abortController) this.abortController = null;
			this.stopRequested = false;
		}
	}

	stop(): void {
		if (!this.running) return;
		this.stopRequested = true;
		this.abortController?.abort();
	}
}
