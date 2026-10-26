// Reading the files an administrator chooses for plugins, and saving the
// ones the Server hands back.
import type { PluginPackageUpload } from './server-administration.svelte';

/** Base64 of a file's bytes, built in slices so a large zip does not overflow the call stack. */
export async function fileToBase64(file: Blob): Promise<string> {
	const bytes = new Uint8Array(await file.arrayBuffer());
	let binary = '';
	for (let i = 0; i < bytes.length; i += 0x8000) binary += String.fromCharCode(...bytes.subarray(i, i + 0x8000));
	return btoa(binary);
}

/** A zip goes as an archive, anything else as the JSON file's text. */
export async function readPluginPackageFile(file: File): Promise<PluginPackageUpload> {
	const isZip = file.name.toLowerCase().endsWith('.zip') || file.type === 'application/zip' || file.type === 'application/x-zip-compressed';
	return isZip ? { archive: await fileToBase64(file) } : { document: await file.text() };
}

/** Save what the Server sent under the name it gave. */
export function saveBlob(name: string, blob: Blob): void {
	const url = URL.createObjectURL(blob);
	const link = document.createElement('a');
	link.href = url;
	link.download = name;
	document.body.appendChild(link);
	link.click();
	link.remove();
	setTimeout(() => URL.revokeObjectURL(url), 1000);
}
