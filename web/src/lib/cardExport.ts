import { downloadFolderSettings } from '$lib/features/export/download-folder.svelte';
import { saveBlob } from '$lib/features/export/save-target';
import { cardExportRequestBody, type CardExportSettings } from '$lib/cardExportRequest';

export {
	DEFAULT_CARD_EXPORT_SETTINGS,
	normalizeCardExportSettings,
	parseCardExportSettings,
	type CardExportSettings,
	type CardLayout
} from '$lib/cardExportRequest';

type ApiFetch = (path: string, init?: RequestInit) => Promise<Response>;

function filenameFromResponse(response: Response): string {
	const disposition = response.headers.get('content-disposition') ?? '';
	const match = disposition.match(/filename="([^"]+)"/i);
	if (match?.[1]) return match[1];
	const stamp = new Date().toISOString().replace(/[-:]/g, '').replace(/\..+/, '');
	return `inku-card-${stamp}.png`;
}

async function requestCard(
	apiFetch: ApiFetch,
	id: string,
	settings: CardExportSettings,
	height?: number
): Promise<Response> {
	const response = await apiFetch('/api/history/export-card', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(cardExportRequestBody(id, settings, height))
	});
	if (!response.ok) {
		const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
		throw new Error(typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`);
	}
	return response;
}

/** The card as a PNG, `height` pixels tall (the layout's own size when absent). */
export async function fetchCardPng(
	apiFetch: ApiFetch,
	id: string,
	settings: CardExportSettings,
	height?: number
): Promise<Blob> {
	const blob = await (await requestCard(apiFetch, id, settings, height)).blob();
	// The clipboard takes the type from the blob, so it must say PNG.
	return blob.type === 'image/png' ? blob : new Blob([blob], { type: 'image/png' });
}

export async function downloadCard(
	apiFetch: ApiFetch,
	id: string,
	settings: CardExportSettings
): Promise<void> {
	const response = await requestCard(apiFetch, id, settings);
	const blob = await response.blob();
	// Same single path as every other download -- see features/export/save-target.
	await saveBlob(blob, filenameFromResponse(response), {
		enabled: downloadFolderSettings.enabled,
	});
}
