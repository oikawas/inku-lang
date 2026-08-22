import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { LineageGraph, NearbyWork } from './types.ts';

export type HistoryStarProjection = {
	id?: string;
	starred?: boolean;
	note?: string | null;
};

export type HistoryForRevisionProjection = {
	id?: string;
	for_revision?: boolean;
};

export type HistoryForShareProjection = {
	id?: string;
	for_share?: boolean;
	share_group_id?: string | null;
};

/**
 * Route-instance owner for lineage queries and nearby-work projection.
 *
 * One request counter covers base, branch, and overview loads because all three
 * write one graph. A newer question or reset invalidates every older answer.
 * The owner deliberately has no HistoryManager, route state, or UI actions.
 */
export class LineageQueryState {
	graph = $state<LineageGraph | null>(null);
	loading = $state(false);
	error = $state<string | null>(null);
	nearby = $state<NearbyWork[]>([]);

	private loadedFocus: string | null = null;
	private requestId = 0;
	private nearbyRequestId = 0;
	private nearbyLoadedId: string | null = null;
	private readonly apiFetch: ApiFetch;

	constructor(apiFetch: ApiFetch) {
		this.apiFetch = apiFetch;
	}

	/**
	 * Clear the graph and invalidate any graph answer already in flight.
	 *
	 * Nearby works have their own identity and are driven by the displayed
	 * history id, so a target reset does not clear them ahead of that effect.
	 */
	reset(): void {
		this.requestId += 1;
		this.loading = false;
		this.error = null;
		this.graph = null;
		this.loadedFocus = null;
	}

	load = async (nodeId: string, force = false, descendantDepth = 3): Promise<void> => {
		if (!nodeId || (!force && this.loadedFocus === nodeId)) return;
		const requestId = ++this.requestId;
		this.loading = true;
		this.error = null;
		try {
			const url = `/api/lineage/${encodeURIComponent(nodeId)}?descendant_depth=${descendantDepth}&node_limit=200`;
			const response = await this.apiFetch(url, { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const graph = await response.json() as LineageGraph;
			if (requestId !== this.requestId) return;
			this.graph = graph;
			this.loadedFocus = nodeId;
		} catch (cause) {
			if (requestId === this.requestId) {
				this.error = cause instanceof Error ? cause.message : String(cause);
			}
		} finally {
			if (requestId === this.requestId) this.loading = false;
		}
	};

	loadBranch = async (nodeId: string): Promise<void> => {
		if (!this.graph) return;
		const focusNodeId = this.graph.focus_node_id;
		const requestId = ++this.requestId;
		this.loading = true;
		this.error = null;
		try {
			const response = await this.apiFetch(
				`/api/lineage/${encodeURIComponent(nodeId)}?descendant_depth=1&node_limit=200`,
				{ cache: 'no-store' }
			);
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const branch = await response.json() as LineageGraph;
			if (requestId !== this.requestId || this.graph?.focus_node_id !== focusNodeId) return;
			const nodes = new Map(this.graph.nodes.map((node) => [node.id, node]));
			const edges = new Map(this.graph.edges.map((edge) => [edge.id, edge]));
			for (const node of branch.nodes) nodes.set(node.id, node);
			for (const edge of branch.edges) edges.set(edge.id, edge);
			this.graph = { ...this.graph, nodes: [...nodes.values()], edges: [...edges.values()] };
		} catch (cause) {
			if (requestId === this.requestId) {
				this.error = cause instanceof Error ? cause.message : String(cause);
			}
		} finally {
			if (requestId === this.requestId) this.loading = false;
		}
	};

	loadOverview = async (fallbackFocusNodeId: string | null | undefined): Promise<void> => {
		const focusNodeId = this.graph?.focus_node_id ?? fallbackFocusNodeId ?? null;
		if (!focusNodeId || !this.graph) return;
		const childIds = new Set(this.graph.edges.map((edge) => edge.child_node_id));
		const rootNodeId = this.graph.nodes.find((node) => !childIds.has(node.id))?.id ?? focusNodeId;
		const requestId = ++this.requestId;
		this.loading = true;
		this.error = null;
		try {
			const url = `/api/lineage/${encodeURIComponent(rootNodeId)}?descendant_depth=200&node_limit=200`;
			const response = await this.apiFetch(url, { cache: 'no-store' });
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const overview = await response.json() as LineageGraph;
			if (requestId !== this.requestId) return;
			this.graph = { ...overview, focus_node_id: focusNodeId };
			this.loadedFocus = focusNodeId;
		} catch (cause) {
			if (requestId === this.requestId) {
				this.error = cause instanceof Error ? cause.message : String(cause);
			}
		} finally {
			if (requestId === this.requestId) this.loading = false;
		}
	};

	loadNearby = async (historyId: string | null | undefined): Promise<void> => {
		const normalizedHistoryId = historyId ?? null;
		if (normalizedHistoryId === this.nearbyLoadedId) return;
		this.nearbyLoadedId = normalizedHistoryId;
		const requestId = ++this.nearbyRequestId;
		this.nearby = [];
		if (!historyId) return;
		try {
			const response = await this.apiFetch(
				`/api/history/${historyId}/neighbors`,
				{ cache: 'no-store' }
			);
			if (!response.ok) throw new Error(`HTTP ${response.status}`);
			const items = await response.json();
			if (requestId === this.nearbyRequestId) {
				this.nearby = Array.isArray(items) ? items : [];
			}
		} catch {
			if (requestId === this.nearbyRequestId) this.nearby = [];
		}
	};

	applyStarState(item: HistoryStarProjection): void {
		if (!item.id) return;
		const hasNote = Object.prototype.hasOwnProperty.call(item, 'note');
		this.updateHistory(item.id, (history) => ({
			...history,
			starred: item.starred,
			note: hasNote ? item.note : history.note
		}));
	}

	applyForRevisionState(item: HistoryForRevisionProjection): void {
		if (!item.id) return;
		this.updateHistory(item.id, (history) => ({ ...history, for_revision: item.for_revision }));
	}

	applyForShareState(item: HistoryForShareProjection): void {
		if (!item.id) return;
		this.updateHistory(item.id, (history) => ({
			...history,
			for_share: item.for_share,
			share_group_id: item.share_group_id
		}));
	}

	private updateHistory(
		historyId: string,
		update: (history: NonNullable<LineageGraph['nodes'][number]['history']>) => NonNullable<LineageGraph['nodes'][number]['history']>
	): void {
		if (!this.graph) return;
		this.graph = {
			...this.graph,
			nodes: this.graph.nodes.map((node) => node.history?.id === historyId
				? { ...node, history: update(node.history) }
				: node)
		};
	}
}
