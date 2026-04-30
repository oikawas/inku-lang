<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type HistoryItem = {
		id?: string;
		input: string;
		ddl: string | null;
		thinking?: string | null;
		score: { instructions: unknown[] };
		svg: string;
		at: number;
		elapsed_ms?: number;
		stage1_model?: string | null;
		stage2_model?: string | null;
		tokens_in?: number | null;
		tokens_out?: number | null;
		catalog_id?: string | null;
		trashed?: boolean;
	};

	type Props = {
		historyItems: HistoryItem[];
		historyTotal: number;
		historyCursor: number;
		historyPage: number;
		historyTotalPages: number;
		historyNavSpan: number;
		onOpenManager: () => void;
		onNewerPage: () => void | Promise<void>;
		onOlderPage: () => void | Promise<void>;
		onLoadIteration: (index: number) => void;
		historyIndexLabel: (index: number) => number;
		historyModelSummary: (item: HistoryItem) => string;
		formatHistoryDate: (at: number) => string;
		formatElapsed: (ms: number | null | undefined) => string;
		catalogName: (id: string | null | undefined) => string;
		clippedHistorySvg: (item: HistoryItem, scope: string) => string;
		shortModel: (model: string | null | undefined) => string;
	};

	let {
		historyItems,
		historyTotal,
		historyCursor,
		historyPage,
		historyTotalPages,
		historyNavSpan,
		onOpenManager,
		onNewerPage,
		onOlderPage,
		onLoadIteration,
		historyIndexLabel,
		historyModelSummary,
		formatHistoryDate,
		formatElapsed,
		catalogName,
		clippedHistorySvg,
		shortModel
	}: Props = $props();
</script>

{#if historyTotal > 0}
	<div class="history-strip">
		<div class="history-head">
			<button class="history-title-btn" onclick={onOpenManager}>
				{t().historyTitle} <span class="history-count">({historyTotal})</span> ▸
			</button>
			<div class="history-page-nav">
				<button class="ghost-btn history-nav-btn" onclick={onNewerPage} disabled={historyPage <= 0}>{t().historyNewerPage(historyNavSpan)}</button>
				<span class="history-page-indicator">{historyPage + 1} / {historyTotalPages}</span>
				<button class="ghost-btn history-nav-btn" onclick={onOlderPage} disabled={historyPage >= historyTotalPages - 1}>{t().historyOlderPage(historyNavSpan)}</button>
			</div>
		</div>
		<div class="thumb-strip">
			{#each historyItems as it, i (it.id ?? it.at)}
				<button
					class="thumb"
					class:current={i === historyCursor}
					onclick={() => onLoadIteration(i)}
				>
					<div class="thumb-tooltip">
						<div class="tooltip-title">#{historyIndexLabel(i)}</div>
						<div class="tooltip-row"><span>{t().historyTooltipModel}</span><strong>{historyModelSummary(it)}</strong></div>
						<div class="tooltip-row"><span>{t().historyTooltipSavedAt}</span><strong>{formatHistoryDate(it.at)}</strong></div>
						<div class="tooltip-row"><span>{t().historyTooltipSeconds}</span><strong>{formatElapsed(it.elapsed_ms)}</strong></div>
						<div class="tooltip-row"><span>{t().historyTooltipColorCatalog}</span><strong>{catalogName(it.catalog_id)}</strong></div>
					</div>
					<div class="thumb-svg">{@html clippedHistorySvg(it, 'strip')}</div>
					<div class="thumb-meta">
						<span class="thumb-time">{formatElapsed(it.elapsed_ms) !== '-' ? formatElapsed(it.elapsed_ms) : String(historyIndexLabel(i))}</span>
						{#if it.stage2_model}<span class="thumb-model">{shortModel(it.stage2_model)}</span>{/if}
					</div>
					{#if i === historyCursor}
						<div class="thumb-current-badge">{t().historyCurrentBadge}</div>
					{/if}
				</button>
			{/each}
		</div>
	</div>
{/if}

<style>
	.history-strip {
		position: relative;
		z-index: 30;
		border-top: 1px solid var(--border);
		background: var(--bg);
		padding: 8px 16px 10px;
		flex-shrink: 0;
	}
	.history-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 7px;
	}
	.history-title-btn {
		border: 1px solid var(--border2);
		border-radius: 16px;
		background: #fff;
		color: var(--fg2);
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		font-family: inherit;
		padding: 5px 12px;
		box-shadow: 0 1px 3px rgba(0,0,0,0.06);
		transition: background 0.12s, border-color 0.12s, color 0.12s, box-shadow 0.12s;
	}
	.history-title-btn:hover {
		color: var(--fg);
		background: var(--accent-light);
		border-color: var(--accent);
		box-shadow: 0 2px 8px rgba(42,74,114,0.16);
	}
	.history-count { color: var(--fg3); font-weight: 400; }
	.history-page-nav { display: flex; align-items: center; gap: 6px; }
	.history-page-indicator {
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		min-width: 30px;
		text-align: center;
	}
	.history-nav-btn { min-width: 92px; }
	.thumb-strip {
		display: flex;
		gap: 7px;
		overflow: visible;
	}
	.thumb {
		flex-shrink: 0;
		width: 82px;
		border: 2px solid transparent;
		border-radius: var(--r);
		overflow: hidden;
		background: #fff;
		cursor: pointer;
		padding: 0;
		font-family: inherit;
		position: relative;
		transition: border-color 0.1s;
	}
	.thumb:hover { overflow: visible; z-index: 2000; }
	.thumb.current { border-color: var(--accent); }
	.thumb-tooltip {
		position: absolute;
		bottom: calc(100% + 6px);
		left: 50%;
		transform: translateX(-50%) translateY(4px);
		opacity: 0;
		pointer-events: none;
		background: rgba(26,25,23,0.92);
		color: #fff;
		font-size: 11px;
		border-radius: var(--r);
		padding: 8px 10px;
		white-space: nowrap;
		text-align: left;
		width: max-content;
		max-width: min(360px, calc(100vw - 24px));
		z-index: 3000;
		line-height: 1.7;
		transition: opacity 0.15s, transform 0.15s;
		box-shadow: 0 4px 18px rgba(0,0,0,0.18);
	}
	.thumb:hover .thumb-tooltip {
		opacity: 1;
		transform: translateX(-50%) translateY(0);
	}
	.tooltip-title { font-weight: 500; margin-bottom: 3px; }
	.tooltip-row {
		display: grid;
		grid-template-columns: 54px minmax(0, 1fr);
		gap: 8px;
		align-items: baseline;
	}
	.tooltip-row span { color: rgba(255,255,255,0.62); }
	.tooltip-row strong {
		font-weight: 500;
		color: #fff;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.thumb-svg {
		width: 82px;
		height: 58px;
		overflow: hidden;
		overflow: clip;
		clip-path: inset(0);
		contain: paint;
	}
	.thumb-svg :global(svg) {
		width: 100%;
		height: 100%;
		display: block;
		overflow: hidden;
		clip-path: inset(0);
	}
	.thumb-meta {
		padding: 3px 5px;
		border-top: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.thumb-time { font-size: 11px; font-weight: 500; color: var(--fg2); }
	.thumb-model { font-size: 10px; color: var(--fg3); }
	.thumb-current-badge {
		position: absolute;
		bottom: 22px;
		right: 3px;
		background: var(--accent);
		color: #fff;
		font-size: 9px;
		padding: 1px 4px;
		border-radius: 2px;
	}
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: #fff;
		color: var(--fg2);
		font-size: 11px;
		font-family: inherit;
		cursor: pointer;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
