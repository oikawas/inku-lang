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

export type ImageFolderRunOptions<TFile extends FolderFile> = {
	/** Start over: forget which pictures of this folder are done. */
	fromStart: boolean;
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
	/** The last run was stopped, by the author or by a lost connection. */
	interrupted = $state(false);
	current = $state(0);
	total = $state(0);
	activePath = $state('');
	success = $state(0);
	/** Why the last run stopped by itself; null when the author stopped it or it ended. */
	stopReason = $state<string | null>(null);

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

	/** The files of the folder the author picked, as the browser handed them over. */
	pick(files: readonly TFile[]): void {
		if (this.running) return;
		this.pictures = picturesOfFolder(files);
		this.folderName = folderNameOf(files);
		this.interrupted = false;
		this.stopReason = null;
		this.success = 0;
	}

	get record(): ImageFolderRecord | null {
		return this.folderName ? recordOf(this.history, this.folderName) : null;
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

	async run(options: ImageFolderRunOptions<TFile>): Promise<void> {
		if (this.running || this.pictures.length === 0) return;
		const name = this.folderName;
		let record: ImageFolderRecord = options.fromStart || !this.record
			? { name, total: this.pictures.length, done: [], failures: [], updatedAt: Date.now() }
			: { ...this.record, total: this.pictures.length, updatedAt: Date.now() };
		const queue = picturesToPaint(this.pictures, record);
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
		this.interrupted = false;
		this.stopReason = null;
		this.success = 0;
		this.current = 0;
		this.total = queue.length;
		try {
			for (const [index, file] of queue.entries()) {
				if (this.stopRequested) break;
				const key = pictureKey(file);
				this.current = index + 1;
				this.activePath = relativePathOf(file);
				try {
					await options.paintPicture(file, abortController.signal);
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
