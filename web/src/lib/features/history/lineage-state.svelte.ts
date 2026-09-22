import type { ApiFetch } from '../../transport/api-fetch.ts';
import type { LineageGraph, NearbyWork } from './types.ts';

export type LineageOrientation = 'vertical' | 'horizontal';

export type LineageScrollPosition = { left: number; top: number };

function lineageRootId(graph: LineageGraph): string | null {
	const childIds = new Set(graph.edges.map((edge) => edge.child_node_id));
	return graph.nodes.find((node) => !childIds.has(node.id))?.id ?? graph.focus_node_id ?? null;
}

/**
 * Route-lifetime browsing state for one authorized lineage tree.
 *
 * The graph remains owned by LineageQueryState. A response for another root,
 * including a reset after an account or permission change, discards this state
 * rather than attempting to show a remembered branch against unknown data.
 */
export class LineageBrowsingState {
	treeId = $state<string | null>(null);
	expandedNodeIds = $state<string[]>([]);
	overviewOpen = $state(false);
	overviewScale = $state(1);
	orientation = $state<LineageOrientation>('vertical');
	normalScroll = $state<LineageScrollPosition>({ left: 0, top: 0 });
	overviewScroll = $state<LineageScrollPosition>({ left: 0, top: 0 });

	reset(): void {
		this.treeId = null;
		this.expandedNodeIds = [];
		this.overviewOpen = false;
		this.overviewScale = 1;
		this.normalScroll = { left: 0, top: 0 };
		this.overviewScroll = { left: 0, top: 0 };
	}

	reconcileGraph(graph: LineageGraph | null): boolean {
		if (!graph) return false;
		const nextTreeId = lineageRootId(graph);
		if (!nextTreeId || nextTreeId !== this.treeId) {
			this.reset();
			this.treeId = nextTreeId;
			this.expandedNodeIds = graph.focus_node_id ? [graph.focus_node_id] : [];
			return true;
		}
		const available = new Set(graph.nodes.map((node) => node.id));
		const retained = this.expandedNodeIds.filter((id) => available.has(id));
		if (retained.length !== this.expandedNodeIds.length) this.expandedNodeIds = retained;
		return false;
	}

	setScroll(overview: boolean, position: LineageScrollPosition): void {
		if (overview) this.overviewScroll = position;
		else this.normalScroll = position;
	}

	scrollFor(overview: boolean): LineageScrollPosition {
		return overview ? this.overviewScroll : this.normalScroll;
	}
}

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
	private readonly browsingState?: LineageBrowsingState;

	constructor(apiFetch: ApiFetch, browsingState?: LineageBrowsingState) {
		this.apiFetch = apiFetch;
		this.browsingState = browsingState;
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
			const readGraph = async (id: string, depth: number): Promise<LineageGraph> => {
				const response = await this.apiFetch(`/api/lineage/${encodeURIComponent(id)}?descendant_depth=${depth}&node_limit=200`, { cache: 'no-store' });
				if (!response.ok) throw new Error(`HTTP ${response.status}`);
				return await response.json() as LineageGraph;
			};
			const rootId = this.browsingState?.treeId;
			let graph = await readGraph(rootId ?? nodeId, rootId ? 200 : descendantDepth);
			if (rootId && !graph.nodes.some((node) => node.id === nodeId)) {
				// A bounded overview may omit the focus. Both sets must come from
				// fresh authorized responses; never merge remembered artwork here.
				const focus = await readGraph(nodeId, descendantDepth);
				if (lineageRootId(focus) === lineageRootId(graph)) {
					graph = { ...focus,
						nodes: [...new Map([...graph.nodes, ...focus.nodes].map((node) => [node.id, node])).values()],
						edges: [...new Map([...graph.edges, ...focus.edges].map((edge) => [edge.id, edge])).values()]
					};
				} else graph = focus;
			}
			if (requestId !== this.requestId) return;
			this.graph = { ...graph, focus_node_id: nodeId };
			this.loadedFocus = nodeId;
		} catch (cause) {
			if (requestId === this.requestId) {
				this.error = cause instanceof Error ? cause.message : String(cause);
				this.graph = null;
				this.loadedFocus = null;
				this.browsingState?.reset();
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
