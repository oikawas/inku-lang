import type { HistoryItem } from '../../historyManagerState.svelte.ts';

export type LineageNode = {
	id: string;
	state: 'active' | 'lineage_only' | 'tombstone';
	description_hash?: string | null;
	render_hash?: string | null;
	at: number;
	deleted_at?: number | null;
	child_count?: number;
	// 'deleted' is gone permanently; 'not_permitted' still exists and its owner
	// can grant access. Both render as empty cards, so this value distinguishes
	// the cases and tells the reader whether asking can change the outcome.
	redacted?: 'deleted' | 'not_permitted' | null;
	history?: HistoryItem | null;
};

export type LineageEdge = {
	id: string;
	parent_node_id: string;
	child_node_id: string;
	derivation_kind: string;
	metadata?: Record<string, unknown>;
};

export type LineageGraph = {
	focus_node_id: string;
	nodes: LineageNode[];
	edges: LineageEdge[];
};

/** A complete history work the Server found close to the work on screen. */
export type NearbyWork = HistoryItem;
