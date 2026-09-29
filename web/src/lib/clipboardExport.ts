/**
 * Copying the work on the canvas to the clipboard as a bitmap, so it can be
 * pasted into another application.
 *
 * Two shapes, chosen in Settings > Export > Clipboard: the picture alone, or
 * the share card (the card's page shape and seal come from the card settings
 * on the Export tab). The height is the bitmap's, in pixels, for both; the
 * width follows the canvas or card shape.
 *
 * The browser only lets a page write an image to the clipboard in a secure
 * context (https, or localhost). Plain .ts (no runes), so the rules are
 * testable without the compiler.
 */

export type ClipboardExportFormat = 'image' | 'card';

export type ClipboardExportSettings = {
	format: ClipboardExportFormat;
	height: number;
};

export const CLIPBOARD_HEIGHT_MIN = 256;
export const CLIPBOARD_HEIGHT_MAX = 4096;

export const DEFAULT_CLIPBOARD_EXPORT_SETTINGS: ClipboardExportSettings = {
	format: 'image',
	height: 1080
};

const FORMATS: ClipboardExportFormat[] = ['image', 'card'];

export function clampClipboardHeight(value: unknown): number {
	const n = typeof value === 'number' ? value : Number(value);
	if (!Number.isFinite(n)) return DEFAULT_CLIPBOARD_EXPORT_SETTINGS.height;
	return Math.min(CLIPBOARD_HEIGHT_MAX, Math.max(CLIPBOARD_HEIGHT_MIN, Math.round(n)));
}

export function normalizeClipboardExportSettings(value: unknown): ClipboardExportSettings {
	const raw = value && typeof value === 'object' ? value as Partial<ClipboardExportSettings> : {};
	return {
		format: FORMATS.includes(raw.format as ClipboardExportFormat)
			? raw.format as ClipboardExportFormat
			: DEFAULT_CLIPBOARD_EXPORT_SETTINGS.format,
		height: raw.height === undefined ? DEFAULT_CLIPBOARD_EXPORT_SETTINGS.height : clampClipboardHeight(raw.height)
	};
}

export function parseClipboardExportSettings(value: string | null): ClipboardExportSettings {
	if (!value) return { ...DEFAULT_CLIPBOARD_EXPORT_SETTINGS };
	try {
		return normalizeClipboardExportSettings(JSON.parse(value));
	} catch {
		return { ...DEFAULT_CLIPBOARD_EXPORT_SETTINGS };
	}
}

/** A copy refused for a reason the author can act on; its message is that reason. */
export class ClipboardCopyRefused extends Error {}

export type ClipboardEnvironment = {
	isSecureContext: boolean;
	canWrite: boolean;
	hasClipboardItem: boolean;
};

/** Why an image cannot be copied here, or null when it can. */
export function clipboardUnavailableReason(env: ClipboardEnvironment): 'insecure' | 'unsupported' | null {
	if (!env.isSecureContext) return 'insecure';
	if (!env.canWrite || !env.hasClipboardItem) return 'unsupported';
	return null;
}

export function browserClipboardEnvironment(): ClipboardEnvironment {
	return {
		isSecureContext: typeof window !== 'undefined' && window.isSecureContext === true,
		canWrite: typeof navigator !== 'undefined' && typeof navigator.clipboard?.write === 'function',
		hasClipboardItem: typeof ClipboardItem !== 'undefined'
	};
}

/**
 * Write a PNG to the clipboard.
 *
 * The blob is passed as a promise: building it (a server card, or a
 * rasterisation) can outlast the click, and the browser accepts the write
 * only while the click still counts as the user's.
 */
export async function writePngToClipboard(png: Promise<Blob>): Promise<void> {
	await navigator.clipboard.write([new ClipboardItem({ 'image/png': png })]);
}
