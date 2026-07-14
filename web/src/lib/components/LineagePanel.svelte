<script lang="ts">
	import { onMount, tick } from 'svelte';
	import type { HistoryItem } from '$lib/historyManagerState.svelte';
	import HistoryThumbnail from './HistoryThumbnail.svelte';

	export type LineageNode = {
		id: string;
		state: 'active' | 'lineage_only' | 'tombstone';
		description_hash?: string | null;
		render_hash?: string | null;
		at: number;
		deleted_at?: number | null;
		history?: HistoryItem | null;
	};
	export type LineageEdge = {
		id: string;
		parent_node_id: string;
		child_node_id: string;
		derivation_kind: string;
		metadata?: Record<string, unknown>;
	};
	export type LineageGraph = { focus_node_id: string; nodes: LineageNode[]; edges: LineageEdge[] };

	type Props = {
		graph: LineageGraph | null;
		loading: boolean;
		error: string | null;
		isJapanese: boolean;
		onOpenNode: (node: LineageNode) => void | Promise<void>;
		onPromoteNode: (node: LineageNode) => void | Promise<void>;
		onAskTrash: (historyIds: string[]) => void;
		onDetach: () => void;
	};
	type ArrowPath = { id: string; path: string; tombstone: boolean };

	let { graph, loading, error, isJapanese, onOpenNode, onPromoteNode, onAskTrash, onDetach }: Props = $props();
	let lineageColumnsEl = $state<HTMLDivElement | null>(null);
	let resizeObserver: ResizeObserver | null = null;
	let arrowFrame: number | null = null;
	let arrowPaths = $state<ArrowPath[]>([]);
	let checkedHistoryIds = $state<string[]>([]);
	const cardElements = new Map<string, HTMLElement>();

	const nodeById = $derived(new Map((graph?.nodes ?? []).map((node) => [node.id, node])));
	const focusNode = $derived(graph?.nodes.find((node) => node.id === graph.focus_node_id) ?? null);
	const edgeByChild = $derived(new Map((graph?.edges ?? []).map((edge) => [edge.child_node_id, edge])));
	const depthByNode = $derived.by(() => {
		const depths = new Map<string, number>();
		const resolve = (id: string, seen = new Set<string>()): number => {
			if (depths.has(id)) return depths.get(id) ?? 0;
			if (seen.has(id)) return 0;
			seen.add(id);
			const parent = edgeByChild.get(id)?.parent_node_id;
			const depth = parent ? resolve(parent, seen) + 1 : 0;
			depths.set(id, depth);
			return depth;
		};
		for (const node of graph?.nodes ?? []) resolve(node.id);
		return depths;
	});
	const columns = $derived.by(() => {
		const grouped = new Map<number, LineageNode[]>();
		for (const node of graph?.nodes ?? []) {
			const depth = depthByNode.get(node.id) ?? 0;
			grouped.set(depth, [...(grouped.get(depth) ?? []), node]);
		}
		return [...grouped.entries()].sort(([a], [b]) => a - b);
	});

	function shortHash(value?: string | null): string {
		if (!value) return '—';
		const [prefix, digest] = value.split(':', 2);
		return digest ? `${prefix}:${digest.slice(0, 10)}…` : `${value.slice(0, 12)}…`;
	}

	function operationLabel(kind?: string): string {
		const ja: Record<string, string> = { touch_variation: 'タッチ', layout_variation: '構図', reinterpretation: '解釈', model_variation: 'モデル', ddl_edit: 'DDL編集', description_edit: '記述編集', replay: '再描画' };
		const en: Record<string, string> = { touch_variation: 'Touch', layout_variation: 'Layout', reinterpretation: 'Reading', model_variation: 'Model', ddl_edit: 'DDL edit', description_edit: 'Description edit', replay: 'Replay' };
		return (isJapanese ? ja : en)[kind ?? ''] ?? (kind || (isJapanese ? '起点' : 'Root'));
	}

function toggleCheckedHistory(historyId: string): void {
	checkedHistoryIds = checkedHistoryIds.includes(historyId)
		? checkedHistoryIds.filter((id) => id !== historyId)
		: [...checkedHistoryIds, historyId];
}

function askTrashChecked(): void {
	if (checkedHistoryIds.length > 0) onAskTrash([...checkedHistoryIds]);
}

	function updateArrowPaths(): void {
		if (!lineageColumnsEl || !graph) {
			arrowPaths = [];
			return;
		}
		const container = lineageColumnsEl.getBoundingClientRect();
		arrowPaths = graph.edges.flatMap((edge) => {
			const parent = cardElements.get(edge.parent_node_id);
			const child = cardElements.get(edge.child_node_id);
			if (!parent || !child) return [];
			const parentRect = parent.getBoundingClientRect();
			const childRect = child.getBoundingClientRect();
			const x1 = parentRect.right - container.left + 1;
			const y1 = parentRect.top - container.top + parentRect.height / 2;
			const x2 = childRect.left - container.left - 7;
			const y2 = childRect.top - container.top + childRect.height / 2;
			const bend = Math.max(24, (x2 - x1) / 2);
			return [{
				id: edge.id,
				path: `M ${x1} ${y1} C ${x1 + bend} ${y1}, ${x2 - bend} ${y2}, ${x2} ${y2}`,
				tombstone: nodeById.get(edge.parent_node_id)?.state === 'tombstone' || nodeById.get(edge.child_node_id)?.state === 'tombstone',
			}];
		});
	}

	function scheduleArrowUpdate(): void {
		if (typeof window === 'undefined') return;
		if (arrowFrame !== null) window.cancelAnimationFrame(arrowFrame);
		arrowFrame = window.requestAnimationFrame(() => {
			arrowFrame = null;
			updateArrowPaths();
		});
	}

	function registerCard(element: HTMLElement, nodeId: string) {
		cardElements.set(nodeId, element);
		resizeObserver?.observe(element);
		scheduleArrowUpdate();
		return {
			update(nextNodeId: string) {
				if (nextNodeId === nodeId) return;
				cardElements.delete(nodeId);
				nodeId = nextNodeId;
				cardElements.set(nodeId, element);
				scheduleArrowUpdate();
			},
			destroy() {
				resizeObserver?.unobserve(element);
				cardElements.delete(nodeId);
				scheduleArrowUpdate();
			},
		};
	}

	onMount(() => {
		resizeObserver = new ResizeObserver(scheduleArrowUpdate);
		if (lineageColumnsEl) resizeObserver.observe(lineageColumnsEl);
		for (const element of cardElements.values()) resizeObserver.observe(element);
		window.addEventListener('resize', scheduleArrowUpdate);
		scheduleArrowUpdate();
		return () => {
			resizeObserver?.disconnect();
			resizeObserver = null;
			window.removeEventListener('resize', scheduleArrowUpdate);
			if (arrowFrame !== null) window.cancelAnimationFrame(arrowFrame);
		};
	});

	$effect(() => {
		graph?.focus_node_id;
		columns;
		void tick().then(scheduleArrowUpdate);
	});
$effect(() => {
	const available = new Set((graph?.nodes ?? [])
		.filter((node) => node.history?.id && !node.history.trashed)
		.map((node) => node.history?.id as string));
	const next = checkedHistoryIds.filter((id) => available.has(id));
	if (next.join('\n') !== checkedHistoryIds.join('\n')) checkedHistoryIds = next;
});

</script>

<section class="lineage-panel">
	<header>
		<div>
			<h2>{isJapanese ? '作品の系譜' : 'Artwork lineage'}</h2>
			<p>{isJapanese ? '派生の流れを辿り、任意の作品へ戻れます。' : 'Trace derivations and return to any artwork.'}</p>
			{#if graph}<p class="lineage-context">{isJapanese ? '表示中の作品が、次の推敲の親になります。' : 'The displayed artwork will be the parent of your next refinement.'}</p>{/if}
		</div>
<div class="lineage-actions">
	<button class="bulk-trash" type="button" disabled={checkedHistoryIds.length === 0} title={isJapanese ? 'チェックした作品をゴミ箱へ移動' : 'Move checked artworks to trash'} aria-label={isJapanese ? 'チェックした作品をゴミ箱へ移動' : 'Move checked artworks to trash'} onclick={askTrashChecked}>
		<svg viewBox="2 2 20 20" aria-hidden="true"><path d="M3 6h18"></path><path d="M8 6V4h8v2"></path><path d="M6 6l1 15h10l1-15"></path><path d="M10 10v7"></path><path d="M14 10v7"></path></svg>
		{#if checkedHistoryIds.length > 0}<span>{checkedHistoryIds.length}</span>{/if}
	</button>
	<button type="button" onclick={onDetach}>{isJapanese ? '新しい起点にする' : 'Start a new root'}</button>
</div>
	</header>
	{#if loading}
		<div class="lineage-message">{isJapanese ? '系譜を読み込み中…' : 'Loading lineage…'}</div>
	{:else if error}
		<div class="lineage-message error">{error}</div>
	{:else if !graph || graph.nodes.length === 0}
		<div class="lineage-message">{isJapanese ? '保存すると、ここに系譜が表示されます。' : 'Save an artwork to begin its lineage.'}</div>
	{:else}
		<div class="lineage-scroll">
			<div class="lineage-columns" bind:this={lineageColumnsEl}>
				<svg class="lineage-arrows" aria-hidden="true">
					<defs>
						<marker id="lineage-arrowhead" markerWidth="7" markerHeight="7" refX="6" refY="3.5" orient="auto" markerUnits="strokeWidth">
							<path d="M 0 0 L 7 3.5 L 0 7 z"></path>
						</marker>
					</defs>
					{#each arrowPaths as arrow (arrow.id)}
						<path class="lineage-arrow" class:tombstone-arrow={arrow.tombstone} d={arrow.path} marker-end="url(#lineage-arrowhead)"></path>
					{/each}
				</svg>
				{#each columns as [depth, nodes] (depth)}
					<div class="lineage-column">
						<div class="generation">{isJapanese ? `第${depth + 1}世代` : `Generation ${depth + 1}`}</div>
						{#each nodes as node (node.id)}
							{@const edge = edgeByChild.get(node.id)}
							<article use:registerCard={node.id} class="lineage-card" class:focus={node.id === graph.focus_node_id} class:tombstone={node.state === 'tombstone'} class:trashed={!!node.history?.trashed}>
{#if node.history?.id && !node.history.trashed}
	<label class="card-check" aria-label={isJapanese ? '一括操作の対象にする' : 'Check for bulk actions'}>
		<input type="checkbox" checked={checkedHistoryIds.includes(node.history.id)} onclick={(event) => event.stopPropagation()} onpointerdown={(event) => event.stopPropagation()} onchange={() => toggleCheckedHistory(node.history?.id as string)} />
	</label>
{/if}

								<button type="button" class="card-main" disabled={!node.history} aria-current={node.id === graph.focus_node_id ? 'true' : undefined} aria-label={node.history ? `${operationLabel(edge?.derivation_kind)}: ${node.history.source_text ?? node.history.input}` : (isJapanese ? '削除された作品' : 'Deleted artwork')} onclick={() => onOpenNode(node)}>
									<div class="operation">
										<span>{operationLabel(edge?.derivation_kind)}</span>
										<span class="identity-marks">
											{#if node.id === graph.focus_node_id}<span class="active-mark">{isJapanese ? '表示中' : 'Displayed'}</span>{/if}
											{#if node.id !== graph.focus_node_id && node.description_hash && node.description_hash === focusNode?.description_hash}<span class="identity-mark">{isJapanese ? '同じ記述' : 'Same text'}</span>{/if}
											{#if node.id !== graph.focus_node_id && node.render_hash && node.render_hash === focusNode?.render_hash}<span class="identity-mark">{isJapanese ? '同じ版' : 'Same edition'}</span>{/if}
										</span>
									</div>
									<div class="preview">
										{#if node.history?.svg}<HistoryThumbnail item={node.history} scope={`lineage-${node.id}`} size="manager" />{:else}<span>{isJapanese ? '削除済み' : 'Deleted'}</span>{/if}
									</div>
									{#if node.history?.display_label}<div class="display-label">{node.history.display_label}</div>{/if}
									{#if node.history?.trashed}<div class="trash-state">{isJapanese ? 'ゴミ箱（復元可能）' : 'In trash (restorable)'}</div>{/if}
									<div class="meta" title={node.history?.source_text ?? node.history?.input ?? node.description_hash ?? ''}>{node.history?.source_text || node.history?.input || (isJapanese ? '削除された作品' : 'Deleted artwork')}</div>
								</button>
								{#if node.history}
									<details class="node-details">
										<summary>{isJapanese ? '詳細' : 'Details'}</summary>
										<dl>
											<dt>{isJapanese ? '記述' : 'Text'}</dt><dd class="full-source">{node.history.source_text ?? node.history.input}</dd>
											<dt>dh1</dt><dd>{shortHash(node.description_hash)}</dd>
											<dt>rh2</dt><dd>{shortHash(node.render_hash)}</dd>
											<dt>Stage 1</dt><dd>{node.history.stage1_model ?? '—'}</dd>
											<dt>Stage 2</dt><dd>{node.history.stage2_model ?? '—'}</dd>
											<dt>seed</dt><dd>{node.history.render_seed ?? '—'} / {node.history.vary_seed ?? '—'} / {node.history.interpretation_seed ?? '—'}</dd>
											<dt>{isJapanese ? '派生' : 'Derived by'}</dt><dd>{operationLabel(edge?.derivation_kind)}</dd>
										</dl>
									</details>
								{/if}
								{#if node.state === 'lineage_only'}<button class="promote" type="button" onclick={() => onPromoteNode(node)}>{isJapanese ? '履歴に残す' : 'Keep in history'}</button>{/if}
							</article>
						{/each}
					</div>
				{/each}
			</div>
		</div>
		<ol class="sr-only" aria-label={isJapanese ? '作品系譜の階層一覧' : 'Artwork lineage hierarchy'}>
			{#each graph.nodes as node (node.id)}
				{@const edge = edgeByChild.get(node.id)}
				<li>{node.id === graph.focus_node_id ? (isJapanese ? '表示中 — ' : 'Displayed — ') : ''}{operationLabel(edge?.derivation_kind)} — {node.history?.source_text ?? node.history?.input ?? (isJapanese ? '削除された作品' : 'Deleted artwork')}</li>
			{/each}
		</ol>
	{/if}
</section>

<style>
	.lineage-panel { width: 100%; height: 100%; min-width: 0; padding: 22px; overflow: hidden; display: flex; flex-direction: column; color: var(--fg); }
	header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
	h2 { margin: 0 0 4px; font-size: 1.05rem; }
	p { margin: 0; color: var(--fg3); font-size: .82rem; }
	.lineage-context { margin-top: 5px; color: var(--fg2); font-weight: 600; }
	.lineage-actions { display: flex; align-items: center; gap: 8px; }
	header button, .promote { border: 1px solid var(--border2); background: var(--panel); color: var(--fg); border-radius: 7px; padding: 7px 10px; cursor: pointer; }
	.bulk-trash { min-width: 38px; display: inline-flex; align-items: center; justify-content: center; gap: 4px; }
	.bulk-trash svg { width: 16px; height: 16px; fill: none; stroke: currentColor; stroke-width: 1.7; stroke-linecap: round; stroke-linejoin: round; }
	.bulk-trash:disabled { opacity: .4; cursor: default; }
	.lineage-message { margin: auto; color: var(--fg3); }
	.lineage-message.error { color: var(--danger, #9b3d32); }
	.lineage-scroll { min-height: 0; overflow: auto; padding: 8px 18px 24px 8px; }
	.lineage-columns { position: relative; display: flex; align-items: flex-start; gap: 76px; min-width: max-content; }
	.lineage-arrows { position: absolute; inset: 0; z-index: 0; width: 100%; height: 100%; overflow: visible; pointer-events: none; }
	.lineage-arrow { fill: none; stroke: color-mix(in srgb, var(--fg2) 72%, transparent); stroke-width: 1.5; vector-effect: non-scaling-stroke; }
	.lineage-arrow.tombstone-arrow { stroke-dasharray: 5 4; }
	.lineage-arrows marker path { fill: var(--fg2); }
	.lineage-column { position: relative; z-index: 1; width: 210px; min-width: 210px; max-width: 210px; display: grid; gap: 14px; }
	.generation { color: var(--fg3); font-size: .72rem; text-align: center; }
	.lineage-card { position: relative; box-sizing: border-box; width: 210px; min-width: 0; max-width: 210px; overflow: hidden; border: 1px solid var(--border); border-radius: 10px; padding: 8px; background: var(--panel); box-shadow: 0 2px 8px color-mix(in srgb, var(--fg) 8%, transparent); }
	.lineage-card.focus { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 6%, var(--panel)); box-shadow: 0 0 0 2px color-mix(in srgb, var(--accent) 22%, transparent); }
	.lineage-card.tombstone { border-style: dashed; opacity: .72; }
	.lineage-card.trashed { opacity: .62; filter: grayscale(.35); }
	.card-check { position: absolute; z-index: 3; top: 8px; right: 8px; display: grid; place-items: center; padding: 2px; border-radius: 4px; background: color-mix(in srgb, var(--panel) 88%, transparent); cursor: pointer; }
	.card-check input { width: 15px; height: 15px; margin: 0; accent-color: var(--accent); }
	.card-main { display: block; width: 100%; min-width: 0; border: 0; padding: 0; background: transparent; color: inherit; cursor: pointer; text-align: left; font: inherit; }
	.card-main:disabled { cursor: default; }
	.card-main:focus-visible { outline: 2px solid var(--accent); outline-offset: 3px; border-radius: 6px; }
	.operation { padding-right: 22px; min-height: 18px; margin-bottom: 6px; display: flex; justify-content: space-between; gap: 5px; color: var(--fg2); font-size: .7rem; }
	.identity-marks { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 3px; }
	.identity-mark, .active-mark { border-radius: 999px; padding: 1px 5px; font-size: .62rem; }
	.identity-mark { color: var(--fg3); background: var(--bg2); }
	.active-mark { color: var(--accent); background: color-mix(in srgb, var(--accent) 12%, var(--panel)); font-weight: 700; }
	.preview { width: 100%; height: 118px; border-radius: 6px; overflow: hidden; background: var(--bg2); }
	.preview :global(.history-thumbnail) { width: 100%; height: 100%; aspect-ratio: auto; }
	.preview :global(svg) { width: 100%; height: 100%; display: block; }
	.preview span { height: 100%; display: grid; place-items: center; color: var(--fg3); }
	.trash-state { margin-top: 6px; color: var(--fg3); font-size: .64rem; }
	.display-label { margin-top: 7px; color: var(--fg3); font-size: .65rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.meta { margin-top: 4px; min-width: 0; height: 2.7em; overflow: hidden; font-size: .72rem; line-height: 1.35; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; }
	.node-details { margin-top: 7px; font-size: .66rem; }
	.node-details summary { cursor: pointer; color: var(--fg3); }
	.node-details dl { display: grid; grid-template-columns: auto 1fr; gap: 2px 6px; margin: 6px 0 0; }
	.node-details dt { color: var(--fg3); }
	.node-details dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
	.full-source { max-height: 7em; overflow: auto; white-space: pre-wrap; }
	.promote { width: 100%; margin-top: 7px; font-size: .68rem; }
	.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
</style>
