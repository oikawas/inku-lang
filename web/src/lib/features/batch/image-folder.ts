/**
 * The picture batch: every picture in a folder the author picks, painted one
 * after another the way the picture tab paints one.
 *
 * A browser cannot open a folder from a typed path. It reads one only when the
 * author picks it in the browser's own dialog (`<input webkitdirectory>`), and
 * it cannot open that folder again by itself later. So the history keeps what a
 * folder was -- its name, its pictures and which of them are done -- and a
 * resume asks the author to pick the folder again, then skips the done ones.
 *
 * showDirectoryPicker() could keep a handle, but only on https or localhost;
 * 5173 is served over plain http (author's choice, 2026-10-25).
 *
 * The history lives in this browser's localStorage: the folder is on this
 * computer, so another computer could not resume it anyway.
 */

/** The formats the picture tab takes (its file input's accept list). */
const PICTURE_FILE = /\.(jpe?g|png|gif|tiff?)$/i;

export const IMAGE_FOLDER_HISTORY_LIMIT = 10;
const HISTORY_STORAGE_KEY = 'inku.batch.imageFolders.v1';
const SOURCE_STORAGE_KEY = 'inku.batch.source.v1';

export type BatchSource = 'text' | 'image';

/** The part of a File the batch reads; tests build these without a browser. */
export type FolderFile = {
	name: string;
	size: number;
	lastModified: number;
	webkitRelativePath?: string;
};

export type ImageFolderFailure = { key: string; path: string; message: string };

export type ImageFolderRecord = {
	/** The folder's own name, the first part of every relative path. */
	name: string;
	total: number;
	/** Keys of the pictures painted and saved. */
	done: string[];
	/** Pictures that failed in the last run; they are painted again on resume. */
	failures: ImageFolderFailure[];
	updatedAt: number;
};

export function relativePathOf(file: FolderFile): string {
	return file.webkitRelativePath || file.name;
}

/**
 * Which picture this is, across two picks of the same folder. The path inside
 * the folder alone would call a replaced file done; size and time tell it apart.
 */
export function pictureKey(file: FolderFile): string {
	return `${relativePathOf(file)}|${file.size}|${file.lastModified}`;
}

/** The folder's name: the first part of the relative paths. */
export function folderNameOf(files: readonly FolderFile[]): string {
	const path = files.map(relativePathOf).find((item) => item.includes('/'));
	return path ? path.split('/')[0] : '';
}

/**
 * The pictures of a picked folder, in the order they are painted: by the path
 * inside the folder, with numbers compared as numbers (2 before 10), so the
 * order matches what Finder shows. Hidden files (".DS_Store", "._x.jpg") and
 * files of other kinds are left out.
 */
export function picturesOfFolder<T extends FolderFile>(files: readonly T[]): T[] {
	return files
		.filter((file) => PICTURE_FILE.test(file.name) && !relativePathOf(file).split('/').some((part) => part.startsWith('.')))
		.sort((a, b) => relativePathOf(a).localeCompare(relativePathOf(b), undefined, { numeric: true, sensitivity: 'base' }));
}

/** The pictures still to paint: everything not done, failures included. */
export function picturesToPaint<T extends FolderFile>(pictures: readonly T[], record: ImageFolderRecord | null): T[] {
	if (!record) return [...pictures];
	const done = new Set(record.done);
	return pictures.filter((file) => !done.has(pictureKey(file)));
}

/** The newest first, one entry per folder name, at most ten. */
export function rememberFolder(history: readonly ImageFolderRecord[], record: ImageFolderRecord): ImageFolderRecord[] {
	return [record, ...history.filter((item) => item.name !== record.name)].slice(0, IMAGE_FOLDER_HISTORY_LIMIT);
}

export function recordOf(history: readonly ImageFolderRecord[], name: string): ImageFolderRecord | null {
	return history.find((item) => item.name === name) ?? null;
}

function isRecord(value: unknown): value is ImageFolderRecord {
	if (!value || typeof value !== 'object') return false;
	const item = value as Partial<ImageFolderRecord>;
	return typeof item.name === 'string' && typeof item.total === 'number' && typeof item.updatedAt === 'number'
		&& Array.isArray(item.done) && item.done.every((key) => typeof key === 'string')
		&& Array.isArray(item.failures);
}

type StorageLike = Pick<Storage, 'getItem' | 'setItem'>;

function storage(): StorageLike | null {
	try {
		return typeof localStorage === 'undefined' ? null : localStorage;
	} catch {
		return null;
	}
}

export function loadFolderHistory(store: StorageLike | null = storage()): ImageFolderRecord[] {
	try {
		const parsed: unknown = JSON.parse(store?.getItem(HISTORY_STORAGE_KEY) ?? '[]');
		return Array.isArray(parsed) ? parsed.filter(isRecord).slice(0, IMAGE_FOLDER_HISTORY_LIMIT) : [];
	} catch {
		return [];
	}
}

export function saveFolderHistory(history: readonly ImageFolderRecord[], store: StorageLike | null = storage()): void {
	try {
		store?.setItem(HISTORY_STORAGE_KEY, JSON.stringify(history));
	} catch {
		// Private mode or a full store: the run goes on, only its resume is lost.
	}
}

export function loadBatchSource(store: StorageLike | null = storage()): BatchSource {
	try {
		return store?.getItem(SOURCE_STORAGE_KEY) === 'image' ? 'image' : 'text';
	} catch {
		return 'text';
	}
}

export function saveBatchSource(source: BatchSource, store: StorageLike | null = storage()): void {
	try {
		store?.setItem(SOURCE_STORAGE_KEY, source);
	} catch {
		// The switch still works for this page; it only starts at "text" next time.
	}
}
