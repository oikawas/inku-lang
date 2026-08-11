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

export async function downloadCard(
	apiFetch: ApiFetch,
	id: string,
	settings: CardExportSettings
): Promise<void> {
	const response = await apiFetch('/api/history/export-card', {
		method: 'POST',
		headers: { 'Content-Type': 'application/json' },
		body: JSON.stringify(cardExportRequestBody(id, settings))
	});
	if (!response.ok) {
		const payload = await response.json().catch(() => null) as { detail?: unknown } | null;
		throw new Error(typeof payload?.detail === 'string' ? payload.detail : `HTTP ${response.status}`);
	}
	const blob = await response.blob();
	// Same single path as every other download -- see features/export/save-target.
	await saveBlob(blob, filenameFromResponse(response), {
		enabled: downloadFolderSettings.enabled,
	});
}
