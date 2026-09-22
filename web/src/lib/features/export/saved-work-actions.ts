import { t } from '$lib/i18n/index.svelte';
import { downloadAnimation, type AnimationExportSettings } from '$lib/animationExport';
import { downloadCard } from '$lib/cardExport';
import { type SheetVariant } from '$lib/contactSheet';
import { runContactSheet } from '$lib/features/contact-sheet/run';
import { createExportActions, type SvgProfile } from '$lib/features/export/download';
import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
import { saveBlob } from '$lib/features/export/save-target';
import type { SavedWorkExportSnapshot } from '$lib/features/export/saved-work';
import { exportSettings } from '$lib/features/export/settings.svelte';
import type { LineageGraph } from '$lib/features/history/types';
import type { HistoryItem } from '$lib/historyManagerState.svelte';
import { DEFAULT_CANVAS_ASPECT_ID, normalizeCanvasAspectId } from '$lib/plugins/system/canvas-aspect';

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

export type SavedWorkExportActionsDeps = {
	apiFetch: ApiFetch;
	catalogName: (id: string | null | undefined) => string;
	formatDate: (at: number) => string;
	previewText: (text: string) => string;
};

function savedWorkFilename(item: HistoryItem, extension: string, size?: number): string {
	const at = new Date(item.at);
	const stamp = [
		at.getFullYear(),
		String(at.getMonth() + 1).padStart(2, '0'),
		String(at.getDate()).padStart(2, '0'),
		'-',
		String(at.getHours()).padStart(2, '0'),
		String(at.getMinutes()).padStart(2, '0'),
	].join('');
	const id = (item.id ?? 'saved').slice(0, 12);
	return `inku-${id}-${stamp}${size ? `-${size}` : ''}.${extension}`;
}

function numericSeed(value: number | string | null | undefined): number | null {
	if (value == null || value === '') return null;
	const parsed = Number(value);
	return Number.isFinite(parsed) ? parsed : null;
}

async function responseError(response: Response): Promise<Error> {
	const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
	return new Error(typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`);
}

/** Shared callbacks for saved-work export surfaces. Each action validates its
 * exact snapshot against a fresh authorized history response before exporting. */
export function makeSavedWorkExportActions(deps: SavedWorkExportActionsDeps) {
	const validatedSnapshots = new WeakMap<SavedWorkExportSnapshot, HistoryItem[]>();

	function usableHistory(item: HistoryItem | null | undefined): item is HistoryItem {
		return Boolean(item?.id && !item.trashed && item.lineage_state !== 'tombstone');
	}

	async function legacySavedWork(id: string): Promise<HistoryItem | null> {
		const response = await deps.apiFetch(
			`/api/history?anchor_id=${encodeURIComponent(id)}&limit=1&include_svg=false`,
			{ cache: 'no-store' },
		);
		if (!response.ok) return null;
		const payload = await response.json() as { items?: HistoryItem[] };
		const item = payload.items?.find((candidate) => candidate.id === id) ?? null;
		return usableHistory(item) ? item : null;
	}

	async function resolveSavedWork(id: string): Promise<HistoryItem | null> {
		const response = await deps.apiFetch(
			`/api/history/${encodeURIComponent(id)}/lineage?descendant_depth=0&node_limit=1`,
			{ cache: 'no-store' },
		);
		let item: HistoryItem | null = null;
		if (response.ok) {
			const graph = await response.json() as LineageGraph;
			const node = graph.nodes?.find((candidate) => candidate.history?.id === id) ?? null;
			// A graph may retain a node after its work is redacted or tombstoned. Its
			// presence is not authorization to revive the old displayed history.
			if (!node || node.redacted || node.state === 'tombstone' || !usableHistory(node.history)) return null;
			item = node.history;
		} else {
			// Older servers may not have the history-id lineage route. The list
			// fallback is fresh and only succeeds when it returns this exact work.
			item = await legacySavedWork(id);
		}
		return item;
	}

	async function readSnapshot(snapshot: SavedWorkExportSnapshot): Promise<HistoryItem[]> {
		const resolved: HistoryItem[] = [];
		for (const id of snapshot.ids) {
			const item = await resolveSavedWork(id);
			if (!item) throw new Error(t().savedWorkExportUnavailable);
			resolved.push(item);
		}
		return resolved;
	}

	async function resolveSnapshot(snapshot: SavedWorkExportSnapshot, requireSvg = false): Promise<HistoryItem[]> {
		// The menu validates immediately before one action. Consume that exact
		// result once so validation is not followed by the same metadata fetch.
		const resolved = validatedSnapshots.get(snapshot) ?? await readSnapshot(snapshot);
		validatedSnapshots.delete(snapshot);
		if (!requireSvg) return resolved;
		return Promise.all(resolved.map(async (item) => {
			if (item.svg) return item;
			const svgResponse = await deps.apiFetch(`/api/history/${encodeURIComponent(item.id as string)}/svg`, { cache: 'no-store' });
			if (!svgResponse.ok) throw new Error(t().savedWorkExportUnavailable);
			return { ...item, svg: await svgResponse.text() };
		}));
	}

	async function oneSavedWork(snapshot: SavedWorkExportSnapshot, requireSvg = false): Promise<HistoryItem> {
		if (snapshot.ids.length !== 1) throw new Error(t().savedWorkExportUnavailable);
		const [item] = await resolveSnapshot(snapshot, requireSvg);
		return item;
	}

	function exportActionsFor(item: HistoryItem) {
		const aspect = normalizeCanvasAspectId(item.render_canvas_aspect_id ?? item.render_canvas_aspect ?? item.score?.canvas ?? DEFAULT_CANVAS_ASPECT_ID);
		return createExportActions({
			result: () => ({
				svg: item.svg,
				score: item.score,
				history_at: item.at,
				render_seed: numericSeed(item.render_seed),
				composition_seed: numericSeed(item.composition_seed),
			}),
			input: () => item.source_text ?? item.input,
			displayedHistoryItem: () => item,
			apiFetch: deps.apiFetch,
			apiError: responseError,
			exportFilename: (extension, size) => savedWorkFilename(item, extension, size),
			refinementCatalogId: () => item.render_color_catalog_id ?? item.catalog_id ?? '',
			refinementCanvasAspectId: () => aspect,
			effectiveCanvasAspectId: () => aspect,
		});
	}

	return {
		onValidateSnapshot: async (snapshot: SavedWorkExportSnapshot): Promise<boolean> => {
			try {
				validatedSnapshots.set(snapshot, await readSnapshot(snapshot));
				return true;
			} catch {
				return false;
			}
		},
		onDownloadSVG: async (profile: SvgProfile, snapshot: SavedWorkExportSnapshot): Promise<void> => {
			const item = await oneSavedWork(snapshot, true);
			await exportActionsFor(item).downloadSVG(profile);
		},
		onDownloadPNG: async (height: number, snapshot: SavedWorkExportSnapshot): Promise<void> => {
			const item = await oneSavedWork(snapshot, true);
			await exportActionsFor(item).downloadPNG(height);
		},
		onDownloadCard: async (historyId: string, snapshot: SavedWorkExportSnapshot): Promise<void> => {
			if (snapshot.ids.length !== 1 || snapshot.ids[0] !== historyId) throw new Error(t().savedWorkExportUnavailable);
			const item = await oneSavedWork(snapshot);
			await downloadCard(deps.apiFetch, item.id as string, exportSettings.card);
		},
		onDownloadAnimation: async (snapshot: SavedWorkExportSnapshot, settings: AnimationExportSettings, directory?: FileSystemDirectoryHandle): Promise<void> => {
			const items = await resolveSnapshot(snapshot);
			await downloadAnimation(deps.apiFetch, items.map((item) => item.id as string), settings, directory);
		},
		onDownloadContactSheet: async (snapshot: SavedWorkExportSnapshot, variant: SheetVariant): Promise<void> => {
			const items = await resolveSnapshot(snapshot, true);
			const byId = new Map(items.map((item) => [item.id as string, item]));
			await runContactSheet(variant, {
				ids: () => snapshot.ids,
				resolveWork: (id) => byId.get(id) ?? null,
				catalogName: deps.catalogName,
				formatDate: deps.formatDate,
				previewText: deps.previewText,
				save: async (blob, filename) => { await saveBlob(blob, filename, { enabled: downloadFolderSettings.enabled }); },
				labels: {
					title: t().historyContactSheetTitle,
					subtitle: (count, at, page, pages) => t().historyContactSheetSubtitle(count, at, page, pages),
				},
			});
		},
	};
}
