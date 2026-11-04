import type { HistoryItem } from '../../historyManagerState.svelte.ts';
import type { ApiFetch } from '../../transport/api-fetch.ts';

/** Read the saved work independently of the history strip's active filters. */
export async function loadBatchSavedWork(apiFetch: ApiFetch, id: string): Promise<HistoryItem> {
	const query = new URLSearchParams({ offset: '0', limit: '1', include_svg: 'false', anchor_id: id });
	const response = await apiFetch(`/api/history?${query.toString()}`, { cache: 'no-store' });
	if (!response.ok) throw new Error(`History: HTTP ${response.status}`);
	const body = await response.json() as { items?: HistoryItem[] };
	const item = body.items?.find((candidate) => candidate.id === id);
	if (!item) throw new Error('Saved batch work is not in the history response');
	return item;
}
