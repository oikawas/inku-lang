import { getCanvasAspectOption, type CanvasAspectId } from '$lib/plugins/system/canvas-aspect';
import { withPngCaptureDate } from '$lib/pngMetadata';
import { exportSettings } from './settings.svelte';
import { downloadFolderSettings } from './download-folder.svelte';
import { saveBlob, type SaveOutcome } from './save-target';

export type SvgProfile = 'display' | 'editable' | 'compat';

/**
 * Downloading the current artwork as SVG or PNG.
 *
 * The page owns the artwork and the fetch wrapper, so those arrive as getters
 * and callbacks -- the same shape as HistoryManagerState's constructor.  What
 * belongs to exporting (the profile round trip, the canvas rasterisation, the
 * capture-date stamp) lives here.
 */
export type ExportDeps = {
	/**
	 * The artwork currently on the canvas; null when nothing has been drawn.
	 * The two seeds are what say which performance of the score this is, so an
	 * export that redraws has to carry them.
	 */
	result: () => {
		svg: string;
		score: unknown;
		history_at?: number | null;
		render_seed?: number | null;
		composition_seed?: number | null;
	} | null;
	/** The description that produced it, embedded as <desc> in the display profile. */
	input: () => string;
	/** The history item on screen, if the artwork came from history. */
	displayedHistoryItem: () => { id?: string; at?: number } | null;
	apiFetch: (path: string, init?: RequestInit) => Promise<Response>;
	apiError: (r: Response) => Promise<Error>;
	exportFilename: (ext: string, size?: number) => string;
	refinementCatalogId: () => string;
	refinementCanvasAspectId: () => CanvasAspectId;
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

export function createExportActions(deps: ExportDeps) {
	async function downloadSVG(profile: SvgProfile = 'display') {
		const result = deps.result();
		if (!result) return;
		const displayedHistoryItem = deps.displayedHistoryItem();
		let svg = result.svg;
		if (profile === 'display') {
			const desc = `<desc>${escapeXml(deps.input())}</desc>`;
			svg = result.svg.replace(/(<svg[^>]*>)/, `$1${desc}`);
		} else if (displayedHistoryItem?.id) {
			const r = await deps.apiFetch(`/api/history/${displayedHistoryItem.id}/svg?profile=${profile}`);
			if (!r.ok) throw await deps.apiError(r);
			svg = await r.text();
		} else {
			const r = await deps.apiFetch('/api/render-svg', {
				method: 'POST',
				headers: { 'Content-Type': 'application/json' },
				body: JSON.stringify({
					score: result.score,
					catalog_id: deps.refinementCatalogId(),
					canvas_aspect: deps.refinementCanvasAspectId(),
					svg_profile: profile,
					// Both seeds, so the file carries the performance on screen.
					// Neither was sent before, which made the export a different
					// performance of the same score: other marks, drawn by
					// another hand. The renderer decides the placement with
					// composition_seed when there is one and render_seed
					// otherwise (renderer.py:3486), so the raw pair is enough --
					// repeating that rule here would be a second copy of it.
					render_seed: result.render_seed ?? null,
					composition_seed: result.composition_seed ?? null
				})
			});
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
		const pngHeight = Math.max(64, Math.round(size));
		const pngWidth = Math.max(64, Math.round(pngHeight * aspect.ratioW / aspect.ratioH));
		const svg = result.svg.replace(/(<svg)([^>]*)/, (_: string, tag: string, attrs: string) => {
			const a = attrs.replace(/\s+width="[^"]*"/g, '').replace(/\s+height="[^"]*"/g, '');
			return `${tag}${a} width="${pngWidth}" height="${pngHeight}"`;
		});
		const blob = new Blob([svg], { type: 'image/svg+xml' });
		const url  = URL.createObjectURL(blob);
		try {
			await new Promise<void>((resolve, reject) => {
				const canvas = document.createElement('canvas');
				canvas.width = pngWidth; canvas.height = pngHeight;
				const ctx = canvas.getContext('2d')!;
				if (!exportSettings.pngAlphaWhite) {
					ctx.fillStyle = '#ffffff'; ctx.fillRect(0, 0, pngWidth, pngHeight);
				}
				const img = new Image();
				img.onload = () => {
					ctx.drawImage(img, 0, 0, pngWidth, pngHeight);
					canvas.toBlob((b) => {
						if (!b) { reject(new Error('canvas error')); return; }
						// Stamp the artwork's own generation time, not the download time.
						// Read through the getters here rather than reusing the values
						// captured above: rasterisation is async, and the original read
						// this inside the callback.
						const generatedAt = deps.displayedHistoryItem()?.at ?? deps.result()?.history_at ?? Date.now();
						withPngCaptureDate(b, new Date(generatedAt))
							.then((stamped) => triggerDownload(stamped, deps.exportFilename('png', size)))
							.then((outcome) => { deps.onSaved?.(outcome); resolve(); })
							.catch(reject);
					}, 'image/png');
				};
				img.onerror = () => reject(new Error('svg load error'));
				img.src = url;
			});
		} finally { URL.revokeObjectURL(url); }
	}

	return { downloadSVG, downloadPNG };
}
