import type { HistoryItem } from '$lib/historyManagerState.svelte';

// The canvas can show a saved history item or a synthetic status projection
// built from the current result, so every persisted field is optional here.
export type CanvasStatusHistoryItem = Partial<HistoryItem>;
