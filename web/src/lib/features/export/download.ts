import { getCanvasAspectOption, type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import { withPngCaptureDate } from '$lib/pngMetadata';
import { exportSettings } from './settings.svelte';
import { downloadFolderSettings } from './download-folder.svelte';
import { saveBlob, type SaveOutcome } from './save-target';

export type SvgProfile = 'display' | 'editable' | 'compat' | 'live';

/**
 * Downloading the current artwork as SVG or PNG.
 *
 * The page owns the artwork and the fetch wrapper, so those arrive as getters
 * and callbacks -- the same shape as HistoryManagerState's constructor.  What
 * belongs to exporting (the profile round trip, the canvas rasterisation, the
 * capture-date stamp) lives here.
 */
export type ExportDeps = {
	/** The saved work's stored picture; null when there is nothing to export. */
	result: () => {
		svg: string;
		score: unknown;
		history_at?: number | null;
	} | null;
	/** The description that produced it, embedded as <desc> in the display profile. */
	input: () => string;
	/** The saved work being exported. */
	displayedHistoryItem: () => { id?: string; at?: number } | null;
	apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
	apiError: (r: Response) => Promise<Error>;
	exportFilename: (ext: string, size?: number) => string;
	effectiveCanvasAspectId: () => CanvasAspectId;
	/** Told where the file actually landed, so a fallback can be reported. */
	onSaved?: (outcome: SaveOutcome) => void;
};

function escapeXml(s: string): string {
	return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}

// Every file leaves the page through save-target.saveBlob; this only supplies
// the user's setting and hands the outcome to the caller's reporter.
function triggerDownload(blob: Blob, filename: string): Promise<SaveOutcome> {
	return saveBlob(blob, filename, { enabled: downloadFolderSettings.enabled });
}

/**
 * The picture as a PNG, `height` pixels tall and as wide as the canvas shape
 * makes it. A transparent background unless `transparent` is false, in which
 * case it is painted white first.
 */
export function rasterizeSvgToPng(svgText: string, height: number, aspect: { ratioW: number; ratioH: number }, transparent: boolean): Promise<Blob> {
	const pngHeight = Math.max(64, Math.round(height));
	const pngWidth = Math.max(64, Math.round(pngHeight * aspect.ratioW / aspect.ratioH));
	const svg = svgText.replace(/(<svg)([^>]*)/, (_: string, tag: string, attrs: string) => {
		const a = attrs.replace(/\s+width="[^"]*"/g, '').replace(/\s+height="[^"]*"/g, '');
		return `${tag}${a} width="${pngWidth}" height="${pngHeight}"`;
	});
	const url = URL.createObjectURL(new Blob([svg], { type: 'image/svg+xml' }));
	return new Promise<Blob>((resolve, reject) => {
		const canvas = document.createElement('canvas');
		canvas.width = pngWidth; canvas.height = pngHeight;
		const ctx = canvas.getContext('2d')!;
		if (!transparent) {
			ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, pngWidth, pngHeight);
		}
		const img = new Image();
		img.onload = () => {
			ctx.drawImage(img, 0, 0, pngWidth, pngHeight);
			canvas.toBlob((b) => (b ? resolve(b) : reject(new Error('canvas error'))), 'image/png');
		};
		img.onerror = () => reject(new Error('svg load error'));
		img.src = url;
	}).finally(() => URL.revokeObjectURL(url));
}

export function createExportActions(deps: ExportDeps) {
	async function downloadSVG(profile: SvgProfile = 'display') {
		const result = deps.result();
		if (!result) return;
		const displayedHistoryItem = deps.displayedHistoryItem();
		let svg = result.svg;
		if (profile === 'display') {
			const desc = `<desc>${escapeXml(deps.input())}</desc>`;
			svg = result.svg.replace(/(<svg[^>]*>)/, `$1${desc}`);
		} else {
			// Only a saved work is exported, so a profile that redraws asks the
			// server for the work's own record.
			if (!displayedHistoryItem?.id) throw new Error('only a saved work is exported');
			const r = await deps.apiFetch(`/api/history/${displayedHistoryItem.id}/svg?profile=${profile}`);
			if (!r.ok) throw await deps.apiError(r);
			svg = await r.text();
		}
		const outcome = await triggerDownload(new Blob([svg], { type: 'image/svg+xml' }), deps.exportFilename(profile === 'display' ? 'svg' : `${profile}.svg`));
		deps.onSaved?.(outcome);
	}

	async function downloadPNG(size: number) {
		const result = deps.result();
		if (!result) return;
		const aspect = getCanvasAspectOption(deps.effectiveCanvasAspectId());
		const png = await rasterizeSvgToPng(result.svg, size, aspect, exportSettings.pngAlphaWhite);
		// Stamp the artwork's own generation time, not the download time. Read
		// through the getters after the rasterisation, which is asynchronous.
		const generatedAt = deps.displayedHistoryItem()?.at ?? deps.result()?.history_at ?? Date.now();
		const stamped = await withPngCaptureDate(png, new Date(generatedAt));
		deps.onSaved?.(await triggerDownload(stamped, deps.exportFilename('png', size)));
	}

	return { downloadSVG, downloadPNG };
}
