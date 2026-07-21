<script lang="ts">
	import { normalizeTenkei, tenkeiLabel } from '$lib/tenkei';
	import { t } from '$lib/i18n/index.svelte';
	import HistoryThumbnail from '$lib/components/HistoryThumbnail.svelte';

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
		history_visibility?: 'normal' | 'lineage_only';
		lineage_generation?: number | null;
		tenkei?: string | null;
		lineage_state?: 'active' | 'lineage_only' | 'tombstone' | null;
		trashed?: boolean;
		starred?: boolean;
	note?: string | null;
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
		onLatestPage: () => void | Promise<void>;
		onLoadIteration: (index: number) => void;
		onToggleStar: (item: HistoryItem, event?: Event) => void | Promise<void>;
		interactionLocked: boolean;
		historyStarredOnly: boolean;
		onSetStarredOnly: (value: boolean) => void;
		historyIndexLabel: (index: number) => number;
		historyModelStage1Short: (item: HistoryItem) => string;
		historyModelStage1Full: (item: HistoryItem) => string;
		historyModelStage2Full: (item: HistoryItem) => string;
		formatHistoryDate: (at: number) => string;
		catalogName: (id: string | null | undefined) => string;
		isJapanese: boolean;
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
		onLatestPage,
		onLoadIteration,
		onToggleStar,
		interactionLocked,
		historyStarredOnly,
		onSetStarredOnly,
		historyIndexLabel,
		historyModelStage1Short,
		historyModelStage1Full,
		historyModelStage2Full,
		formatHistoryDate,
		catalogName,
		isJapanese
	}: Props = $props();

	let historyCollapsed = $state(false);

	function lineageGenerationLabel(item: HistoryItem): string {
		if (!item.lineage_generation) return isJapanese ? '独立作品' : 'Standalone';
		return isJapanese ? `第${item.lineage_generation}世代` : `Gen. ${item.lineage_generation}`;
	}

	function lineageStateLabel(item: HistoryItem): string {
		if (item.lineage_state === 'lineage_only' || item.history_visibility === 'lineage_only') return isJapanese ? '中間作品' : 'Intermediate';
		if (item.lineage_state === 'tombstone') return isJapanese ? '削除済み' : 'Deleted';
		return item.lineage_generation ? (isJapanese ? '通常作品' : 'Active') : (isJapanese ? '系譜なし' : 'No lineage');
	}

	function handleThumbKeydown(event: KeyboardEvent, index: number) {
		if (event.key !== 'Enter' && event.key !== ' ') return;
		event.preventDefault();
		if (interactionLocked) return;
		onLoadIteration(index);
	}
</script>

{#if historyTotal > 0}
	<div class="history-strip" class:collapsed={historyCollapsed} class:locked={interactionLocked}>
		<div class="history-head">
			<button class="history-title-btn" onclick={onOpenManager} disabled={interactionLocked}>
				{t().historyTitle} <span class="history-count">({historyTotal})</span> ▸
			</button>
			{#if interactionLocked}
				<div class="history-lock-badge" role="status" aria-live="polite">
					<span class="lock-icon" aria-hidden="true">◇</span>
					<span>{t().historyLockedDuringDemo}</span>
				</div>
			{/if}
			<div class="history-head-actions">
				{#if !historyCollapsed}
					<div class="history-page-nav">
						<button
							class="ghost-btn history-filter-btn"
							class:ghost-active={historyStarredOnly}
							onclick={() => onSetStarredOnly(!historyStarredOnly)}
						>{t().historyStarredOnly}</button>
						<button class="ghost-btn history-latest-btn" onclick={onLatestPage} disabled={interactionLocked || historyPage <= 0}>{t().historyLatest}</button>
						<button class="ghost-btn history-nav-btn" onclick={onNewerPage} disabled={interactionLocked || historyPage <= 0}>{t().historyNewerPage(historyNavSpan)}</button>
						<span class="history-page-indicator">{historyPage + 1} / {historyTotalPages}</span>
						<button class="ghost-btn history-nav-btn" onclick={onOlderPage} disabled={interactionLocked || historyPage >= historyTotalPages - 1}>{t().historyOlderPage(historyNavSpan)}</button>
					</div>
				{/if}
				<button
					class="ghost-btn history-collapse-btn"
					onclick={() => (historyCollapsed = !historyCollapsed)}
					aria-label={historyCollapsed ? t().historyExpand : t().historyCollapse}
					title={historyCollapsed ? t().historyExpand : t().historyCollapse}
				>
					{historyCollapsed ? '⌃' : '⌄'}
				</button>
			</div>
		</div>
		{#if !historyCollapsed}
			<div class="thumb-strip">
				{#each historyItems as it, i (it.id ?? it.at)}
					<div
						class="thumb"
						class:current={i === historyCursor}
						onclick={() => !interactionLocked && onLoadIteration(i)}
						onkeydown={(event) => handleThumbKeydown(event, i)}
						role="button"
						tabindex={interactionLocked ? -1 : 0}
					>
						<div class="thumb-tooltip">
							<div class="tooltip-title">#{historyIndexLabel(i)}</div>
							<div class="tooltip-row"><span>Stage 1</span><strong>{historyModelStage1Full(it)}</strong></div>
							<div class="tooltip-row"><span>Stage 2</span><strong>{historyModelStage2Full(it)}</strong></div>
							<div class="tooltip-row"><span>{t().historyTooltipSavedAt}</span><strong>{formatHistoryDate(it.at)}</strong></div>
							<div class="tooltip-row"><span>{isJapanese ? '世代' : 'Gen.'}</span><strong>{lineageGenerationLabel(it)}</strong></div>
							{#if normalizeTenkei(it.tenkei)}<div class="tooltip-row"><span>{isJapanese ? '添景' : 'Staffage'}</span><strong>{tenkeiLabel(normalizeTenkei(it.tenkei)!, isJapanese)}</strong></div>{/if}
							<div class="tooltip-row"><span>{isJapanese ? '状態' : 'State'}</span><strong>{lineageStateLabel(it)}</strong></div>
							<div class="tooltip-row"><span>{t().historyTooltipColorCatalog}</span><strong>{catalogName(it.catalog_id)}</strong></div>
							{#if it.note}<div class="tooltip-note"><span>{t().selectionNoteLabel}</span>{it.note}</div>{/if}
						</div>
						<HistoryThumbnail item={it} scope="strip" size="strip" />
						<button
							class="thumb-star"
							class:starred={!!it.starred}
							onclick={(event) => onToggleStar(it, event)}
							title={it.starred ? t().starOn : t().starOff}
							aria-label={it.starred ? t().starOn : t().starOff}
						>★</button>
						<div class="thumb-meta">
							<span class="thumb-generation">{lineageGenerationLabel(it)}</span>
							<span class="thumb-model" title={historyModelStage1Full(it)}>{historyModelStage1Short(it)}</span>
						</div>
						{#if i === historyCursor}
							<div class="thumb-current-badge">{t().historyCurrentBadge}</div>
						{/if}
					</div>
				{/each}
			</div>
		{/if}
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
	.history-strip.locked {
		background:
			repeating-linear-gradient(135deg, transparent 0, transparent 10px, rgba(122, 91, 47, 0.055) 10px, rgba(122, 91, 47, 0.055) 20px),
			var(--bg);
	}
	.history-strip.collapsed {
		padding: 6px 16px;
	}
	.history-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
		margin-bottom: 7px;
	}
	.history-strip.collapsed .history-head {
		margin-bottom: 0;
	}
	.history-title-btn {
		border: 1px solid var(--border2);
		border-radius: 16px;
		background: var(--panel);
		color: var(--fg2);
		font-size: 12px;
		font-weight: 500;
		cursor: pointer;
		font-family: inherit;
		padding: 5px 12px;
		box-shadow: 0 1px 3px rgba(0,0,0,0.06);
		transition: background 0.12s, border-color 0.12s, color 0.12s, box-shadow 0.12s;
	}
	.history-title-btn:disabled { opacity: 0.45; cursor: not-allowed; }
	.history-title-btn:hover:not(:disabled) {
		color: var(--fg);
		background: var(--accent-light);
		border-color: var(--accent);
		box-shadow: 0 2px 8px rgba(42,74,114,0.16);
	}
	.history-count { color: var(--fg3); font-weight: 400; }
	.history-lock-badge {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		border: 1px solid rgba(122, 91, 47, 0.28);
		border-radius: 999px;
		background: rgba(122, 91, 47, 0.09);
		color: var(--fg2);
		font-size: 11px;
		padding: 4px 10px;
		margin-left: 10px;
	}
	.lock-icon {
		color: var(--fg3);
		font-size: 10px;
	}
	.history-head-actions { display: flex; align-items: center; gap: 8px; }
	.history-page-nav { display: flex; align-items: center; gap: 6px; }
	.history-page-indicator {
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		min-width: 30px;
		text-align: center;
	}
	.history-nav-btn { min-width: 92px; }
	.history-latest-btn { min-width: 54px; }
	.history-filter-btn { min-width: 76px; }
	.ghost-btn.ghost-active { background: var(--fg); color: var(--panel); border-color: var(--fg); }
	.history-collapse-btn {
		width: 28px;
		min-width: 28px;
		height: 24px;
		padding: 0;
		font-size: 14px;
		line-height: 1;
	}
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
		background: var(--panel);
		cursor: pointer;
		padding: 0;
		font-family: inherit;
		position: relative;
		transition: border-color 0.1s;
	}
	.thumb:hover { overflow: visible; z-index: 2000; }
	.thumb.current { border-color: var(--accent); }
	.history-strip.locked .thumb {
		opacity: 0.58;
		cursor: not-allowed;
	}
	.history-strip.locked .thumb::after {
		content: '';
		position: absolute;
		inset: 0;
		border-radius: var(--r);
		background: rgba(247, 245, 239, 0.28);
		pointer-events: none;
		z-index: 18;
	}
	:global([data-theme="dark"]) .history-strip.locked .thumb::after {
		background: rgba(20, 20, 20, 0.22);
	}
	.thumb-star {
		position: absolute;
		top: 3px;
		right: 3px;
		z-index: 20;
		width: 18px;
		height: 18px;
		border: 1px solid rgba(0,0,0,0.12);
		border-radius: 50%;
		background: rgba(255,255,255,0.86);
		color: rgba(40,36,30,0.42);
		font-size: 10px;
		line-height: 1;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.thumb-star.starred { color: #d59b21; background: #fff6ce; border-color: rgba(213,155,33,0.45); }
	.thumb-tooltip {
		position: absolute;
		bottom: calc(100% + 6px);
		left: 50%;
		transform: translateX(-50%) translateY(4px);
		opacity: 0;
		pointer-events: none;
		background: var(--tooltip-bg);
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
	.thumb-meta {
		padding: 3px 5px;
		border-top: 1px solid var(--border);
		display: flex;
		flex-direction: column;
		gap: 1px;
	}
	.thumb-generation { font-size: 10px; font-weight: 650; color: var(--fg2); white-space: nowrap; }
	.thumb-model { font-size: 9px; color: var(--fg3); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
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
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font-size: var(--btn-sm-font-size);
		font-family: inherit;
		cursor: pointer;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
