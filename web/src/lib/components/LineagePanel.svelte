<script lang="ts">
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
		onDetach: () => void;
	};

	let { graph, loading, error, isJapanese, onOpenNode, onPromoteNode, onDetach }: Props = $props();

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
</script>

<section class="lineage-panel">
	<header>
		<div><h2>{isJapanese ? '作品の系譜' : 'Artwork lineage'}</h2><p>{isJapanese ? '派生の流れを辿り、任意の作品へ戻れます。' : 'Trace derivations and return to any artwork.'}</p>{#if graph}<p class="lineage-context">{isJapanese ? '選択中の作品が、次の推敲の親になります。' : 'The focused artwork will be the parent of your next refinement.'}</p>{/if}</div>
		<button type="button" onclick={onDetach}>{isJapanese ? '新しい起点にする' : 'Start a new root'}</button>
	</header>
	{#if loading}
		<div class="lineage-message">{isJapanese ? '系譜を読み込み中…' : 'Loading lineage…'}</div>
	{:else if error}
		<div class="lineage-message error">{error}</div>
	{:else if !graph || graph.nodes.length === 0}
		<div class="lineage-message">{isJapanese ? '保存すると、ここに系譜が表示されます。' : 'Save an artwork to begin its lineage.'}</div>
	{:else}
		<div class="lineage-scroll">
			<div class="lineage-columns">
				{#each columns as [depth, nodes] (depth)}
					<div class="lineage-column">
						<div class="generation">{isJapanese ? `第${depth + 1}世代` : `Generation ${depth + 1}`}</div>
						{#each nodes as node (node.id)}
							{@const edge = edgeByChild.get(node.id)}
							<article class="lineage-card" class:focus={node.id === graph.focus_node_id} class:tombstone={node.state === 'tombstone'} class:trashed={!!node.history?.trashed} aria-current={node.id === graph.focus_node_id ? 'true' : undefined}>
								{#if edge}<span class="connector" class:tombstone-connector={node.state === 'tombstone' || nodeById.get(edge.parent_node_id)?.state === 'tombstone'} aria-hidden="true"></span>{/if}
<div class="operation">
	<span>{operationLabel(edge?.derivation_kind)}</span>
	<span class="identity-marks">
		{#if node.id !== graph.focus_node_id && node.description_hash && node.description_hash === focusNode?.description_hash}<span class="identity-mark">{isJapanese ? '同じ記述' : 'Same text'}</span>{/if}
		{#if node.id !== graph.focus_node_id && node.render_hash && node.render_hash === focusNode?.render_hash}<span class="identity-mark">{isJapanese ? '同じ版' : 'Same edition'}</span>{/if}
	</span>
</div>
<button type="button" class="preview" disabled={!node.history} aria-label={node.history ? `${operationLabel(edge?.derivation_kind)}: ${node.history.source_text ?? node.history.input}` : (isJapanese ? '削除された作品' : 'Deleted artwork')} onclick={() => onOpenNode(node)}>
	{#if node.history?.svg}<HistoryThumbnail item={node.history} scope={`lineage-${node.id}`} size="manager" />{:else}<span>{isJapanese ? '削除済み' : 'Deleted'}</span>{/if}
</button>
{#if node.history?.display_label}<div class="display-label">{node.history.display_label}</div>{/if}
{#if node.history?.trashed}<div class="trash-state">{isJapanese ? 'ゴミ箱（復元可能）' : 'In trash (restorable)'}</div>{/if}
<div class="meta" title={node.history?.source_text ?? node.history?.input ?? node.description_hash ?? ''}>{node.history?.source_text || node.history?.input || (isJapanese ? '削除された作品' : 'Deleted artwork')}</div>
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
{#if node.history}
	<button class="select-target" class:current-target={node.id === graph.focus_node_id} type="button" onclick={() => onOpenNode(node)}>
		{node.id === graph.focus_node_id ? (isJapanese ? '編集対象として選択中' : 'Selected for editing') : (isJapanese ? 'この作品を編集対象にする' : 'Edit from this artwork')}
	</button>
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
				<li>{operationLabel(edge?.derivation_kind)} — {node.history?.source_text ?? node.history?.input ?? (isJapanese ? '削除された作品' : 'Deleted artwork')}</li>
			{/each}
		</ol>
	{/if}
</section>

<style>
	.lineage-panel { width: 100%; height: 100%; min-width: 0; padding: 22px; overflow: hidden; display: flex; flex-direction: column; color: var(--text, #2f2b26); }
	header { display: flex; align-items: flex-start; justify-content: space-between; gap: 16px; margin-bottom: 16px; }
	h2 { margin: 0 0 4px; font-size: 1.05rem; } p { margin: 0; color: var(--fg3); font-size: .82rem; }
	.lineage-context { margin-top: 5px; color: var(--fg2); font-weight: 600; }
	header button, .promote { border: 1px solid var(--border2); background: var(--panel); border-radius: 7px; padding: 7px 10px; cursor: pointer; }
	.lineage-message { margin: auto; color: var(--fg3); } .lineage-message.error { color: var(--danger, #9b3d32); }
	.lineage-scroll { min-height: 0; overflow: auto; padding: 8px 18px 24px 8px; }
	.lineage-columns { display: flex; align-items: flex-start; gap: 58px; min-width: max-content; }
	.lineage-column { width: 210px; min-width: 210px; max-width: 210px; display: grid; gap: 14px; position: relative; }
	.generation { color: var(--fg3); font-size: .72rem; text-align: center; }
	.lineage-card { position: relative; box-sizing: border-box; width: 210px; min-width: 0; max-width: 210px; overflow: hidden; border: 1px solid var(--border); border-radius: 10px; padding: 8px; background: var(--panel); box-shadow: 0 2px 8px color-mix(in srgb, var(--fg) 8%, transparent); }
	.lineage-card.focus { border-color: #8c6447; box-shadow: 0 0 0 2px #8c64472a; }
	.lineage-card.tombstone { border-style: dashed; opacity: .72; }
	.lineage-card.trashed { opacity: .62; filter: grayscale(.35); }
	.connector { position: absolute; left: -59px; top: 76px; width: 58px; height: 1px; background: #a99a86; }
	.connector::after { content: ''; position: absolute; right: -1px; top: -3px; border-left: 6px solid #a99a86; border-top: 3px solid transparent; border-bottom: 3px solid transparent; }
	.connector.tombstone-connector { height: 0; background: transparent; border-top: 1px dashed #a99a86; }
	.operation { font-size: .7rem; color: #795f4b; margin-bottom: 6px; display: flex; justify-content: space-between; gap: 5px; }
	.identity-marks { display: flex; flex-wrap: wrap; justify-content: flex-end; gap: 3px; }
	.identity-mark { color: var(--muted, #756d62); background: var(--panel-soft, #ece7de); border-radius: 999px; padding: 1px 5px; font-size: .62rem; }
	.preview { width: 100%; height: 118px; border: 0; border-radius: 6px; padding: 0; overflow: hidden; background: var(--bg2); cursor: pointer; }
	.preview:disabled { cursor: default; }
	.preview :global(.history-thumbnail) { width: 100%; height: 100%; aspect-ratio: auto; }
	.preview :global(svg) { width: 100%; height: 100%; display: block; }
	.preview span { height: 100%; display: grid; place-items: center; color: #81786c; }
	.trash-state { margin-top: 6px; color: var(--fg3); font-size: .64rem; }
	.display-label { margin-top: 7px; color: var(--muted, #756d62); font-size: .65rem; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
	.meta { margin-top: 4px; min-width: 0; height: 2.7em; overflow: hidden; font-size: .72rem; line-height: 1.35; overflow-wrap: anywhere; display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; line-clamp: 2; }
	.node-details { margin-top: 7px; font-size: .66rem; }
	.node-details summary { cursor: pointer; color: var(--muted, #756d62); }
	.node-details dl { display: grid; grid-template-columns: auto 1fr; gap: 2px 6px; margin: 6px 0 0; }
	.node-details dt { color: var(--muted, #756d62); }
	.node-details dd { min-width: 0; margin: 0; overflow-wrap: anywhere; }
	.full-source { max-height: 7em; overflow: auto; white-space: pre-wrap; }
	.sr-only { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0, 0, 0, 0); white-space: nowrap; border: 0; }
	.select-target, .promote { width: 100%; margin-top: 7px; border: 1px solid var(--border2); border-radius: 7px; padding: 7px 8px; background: var(--panel); color: var(--fg); cursor: pointer; font-size: .68rem; }
	.select-target.current-target { border-color: var(--accent); background: color-mix(in srgb, var(--accent) 10%, var(--panel)); color: var(--accent); font-weight: 650; }
</style>
