/**
 * The one place a file leaves the page.
 *
 * Four call sites used to build their own `<a download>`; four sites deciding
 * separately where a file goes is four chances to drift, so they all come
 * through saveBlob() now. The choice is made once, here.
 *
 * The folder is a FileSystemDirectoryHandle from showDirectoryPicker(). It is a
 * live browser object: it cannot be JSON, so it cannot go to the server and
 * cannot go in localStorage. IndexedDB stores structured clones, so it lives
 * there, per browser and per origin. The server holds only the intent and the
 * folder's display name -- see downloadFolderSettings.
 *
 * Chromium only, by the author's ruling (2026-08-02). Firefox and Safari have no
 * showDirectoryPicker, so they keep falling through to the browser's own
 * download folder and the setting is not offered to them.
 */

// The File System Access API is not in TypeScript's DOM lib. Declared here
// rather than pulling in @types/wicg-file-system-access, which would be a new
// dependency for four signatures. Every use is guarded by a runtime check,
// because these really are absent outside Chromium.
type FileSystemPermissionOptions = { mode: 'read' | 'readwrite' };

declare global {
	interface Window {
		showDirectoryPicker?: (options?: FileSystemPermissionOptions) => Promise<FileSystemDirectoryHandle>;
	}
	interface FileSystemDirectoryHandle {
		queryPermission?: (options?: FileSystemPermissionOptions) => Promise<PermissionState>;
		requestPermission?: (options?: FileSystemPermissionOptions) => Promise<PermissionState>;
	}
}

const DB_NAME = 'inku-export';
const DB_VERSION = 1;
const STORE = 'handles';
const HANDLE_KEY = 'download-directory';

export type SaveOutcome =
	/** Written into the folder the user picked. */
	| { kind: 'folder'; folderName: string }
	/** Went to the browser's own download folder, and why. */
	| { kind: 'browser'; reason: 'unsupported' | 'disabled' | 'no-folder' | 'denied' | 'failed' };

export function supportsDirectoryPicker(): boolean {
	return typeof window !== 'undefined' && typeof window.showDirectoryPicker === 'function';
}

function openDatabase(): Promise<IDBDatabase> {
	return new Promise((resolve, reject) => {
		const request = indexedDB.open(DB_NAME, DB_VERSION);
		request.onupgradeneeded = () => {
			if (!request.result.objectStoreNames.contains(STORE)) request.result.createObjectStore(STORE);
		};
		request.onsuccess = () => resolve(request.result);
		request.onerror = () => reject(request.error);
	});
}

async function withStore<T>(
	mode: IDBTransactionMode,
	run: (store: IDBObjectStore) => IDBRequest,
): Promise<T | null> {
	try {
		const database = await openDatabase();
		return await new Promise<T | null>((resolve, reject) => {
			const transaction = database.transaction(STORE, mode);
			const request = run(transaction.objectStore(STORE));
			request.onsuccess = () => resolve((request.result as T) ?? null);
			request.onerror = () => reject(request.error);
			transaction.oncomplete = () => database.close();
		});
	} catch {
		// Private mode, a blocked upgrade, a browser without IndexedDB: the caller
		// falls back to the browser's download folder rather than failing the save.
		return null;
	}
}

export async function storedDirectoryHandle(): Promise<FileSystemDirectoryHandle | null> {
	return withStore<FileSystemDirectoryHandle>('readonly', (store) => store.get(HANDLE_KEY));
}

export async function rememberDirectoryHandle(handle: FileSystemDirectoryHandle): Promise<void> {
	await withStore('readwrite', (store) => store.put(handle, HANDLE_KEY));
}

export async function forgetDirectoryHandle(): Promise<void> {
	await withStore('readwrite', (store) => store.delete(HANDLE_KEY));
}

/** Ask for the folder. Returns null when the user dismissed the picker. */
export async function pickDirectory(): Promise<FileSystemDirectoryHandle | null> {
	const picker = window.showDirectoryPicker;
	if (!picker) return null;
	try {
		const handle = await picker.call(window, { mode: 'readwrite' });
		await rememberDirectoryHandle(handle);
		return handle;
	} catch {
		// AbortError when dismissed; anything else is equally "no folder chosen".
		return null;
	}
}

/**
 * Permission expires -- on a new tab, after a restart, or when the user revokes
 * it -- so it is re-checked on every save rather than once when the folder was
 * picked.
 */
async function ensureWritable(handle: FileSystemDirectoryHandle): Promise<boolean> {
	const options = { mode: 'readwrite' as const };
	try {
		if ((await handle.queryPermission?.(options)) === 'granted') return true;
		return (await handle.requestPermission?.(options)) === 'granted';
	} catch {
		return false;
	}
}

function triggerBrowserDownload(blob: Blob, filename: string): void {
	const url = URL.createObjectURL(blob);
	const anchor = document.createElement('a');
	anchor.href = url;
	anchor.download = filename;
	anchor.click();
	URL.revokeObjectURL(url);
}

/**
 * Save one file. Every download in the app goes through here.
 *
 * `enabled` and `folderName` come from the user's settings; the handle comes
 * from IndexedDB. When anything is missing or permission is refused, the file
 * still lands in the browser's download folder and the outcome says so, so the
 * caller can tell the user it went somewhere other than the folder they picked.
 */
export async function saveBlob(
	blob: Blob,
	filename: string,
	options: { enabled?: boolean } = {},
): Promise<SaveOutcome> {
	if (!supportsDirectoryPicker()) {
		triggerBrowserDownload(blob, filename);
		return { kind: 'browser', reason: 'unsupported' };
	}
	if (options.enabled === false) {
		triggerBrowserDownload(blob, filename);
		return { kind: 'browser', reason: 'disabled' };
	}
	const handle = await storedDirectoryHandle();
	if (!handle) {
		triggerBrowserDownload(blob, filename);
		return { kind: 'browser', reason: 'no-folder' };
	}
	if (!(await ensureWritable(handle))) {
		triggerBrowserDownload(blob, filename);
		return { kind: 'browser', reason: 'denied' };
	}
	try {
		const file = await handle.getFileHandle(filename, { create: true });
		const writable = await file.createWritable();
		await writable.write(blob);
		await writable.close();
		return { kind: 'folder', folderName: handle.name };
	} catch {
		triggerBrowserDownload(blob, filename);
		return { kind: 'browser', reason: 'failed' };
	}
}
