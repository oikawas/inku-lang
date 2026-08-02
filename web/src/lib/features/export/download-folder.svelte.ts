// The download-folder setting, split the way the browser forces it to split.
//
// The server can hold "this user wants a folder" and "the folder was called X".
// It cannot hold the folder itself: a FileSystemDirectoryHandle is a live
// browser object, so it stays in IndexedDB, per browser and per origin. On
// another browser or another machine the user picks again -- the settings panel
// has to say so, because a setting that silently does nothing elsewhere is the
// worst of the options.
//
// Key, default, state and the round trip stay together -- see
// features/color-catalog/settings.svelte.ts for why.
import {
	forgetDirectoryHandle,
	pickDirectory,
	storedDirectoryHandle,
	supportsDirectoryPicker,
} from './save-target';

class DownloadFolderSettings {
	/** Mirrors the server's download_folder_enabled for this user. */
	enabled = $state(false);
	/** The name the server remembers, so the panel can name the folder before IndexedDB answers. */
	name = $state<string | null>(null);
	/** Whether this browser still holds a handle. Only meaningful after refresh(). */
	hasHandle = $state(false);

	get supported(): boolean {
		return supportsDirectoryPicker();
	}

	/** True when the user asked for a folder but this browser has none to write to. */
	get needsPicking(): boolean {
		return this.supported && this.enabled && !this.hasHandle;
	}

	applyUser = (user: { download_folder_enabled?: boolean; download_folder_name?: string | null } | null) => {
		this.enabled = user?.download_folder_enabled === true;
		this.name = user?.download_folder_name ?? null;
	};

	refresh = async () => {
		if (!this.supported) {
			this.hasHandle = false;
			return;
		}
		this.hasHandle = (await storedDirectoryHandle()) !== null;
	};

	/** Returns the chosen folder's name, or null when the user dismissed the picker. */
	choose = async (): Promise<string | null> => {
		const handle = await pickDirectory();
		if (!handle) return null;
		this.hasHandle = true;
		this.name = handle.name;
		return handle.name;
	};

	clear = async () => {
		await forgetDirectoryHandle();
		this.hasHandle = false;
		this.name = null;
	};
}

export const downloadFolderSettings = new DownloadFolderSettings();
