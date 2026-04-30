<script lang="ts">
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
		trashed?: boolean;
		starred?: boolean;
	};

	type Props = {
		historyManagerView: 'active' | 'trash';
		historyManagerTab: 'thumbs' | 'list';
		historyManagerPage: number;
		historyManagerLoading: boolean;
		historyManagerTotalPages: number;
		historyManagerOffset: number;
		historyManagerShownTo: number;
		managedHistoryItems: HistoryItem[];
		managedHistoryTotal: number;
		managerTrashTotal: number;
		trashTotal: number;
		selectedHistoryIds: string[];
		historySearch: string;
		historyManagerStarredOnly: boolean;
		onClose: () => void;
		onSetView: (view: 'active' | 'trash') => void;
		onSetPage: (page: number) => void;
		onSetStarredOnly: (value: boolean) => void;
		onSelectAll: () => void;
		onAskTrash: (ids: string[]) => void;
		onAskRestore: (ids: string[]) => void;
		onAskPermanentDelete: (ids: string[]) => void;
		onToggleSelection: (id: string) => void;
		onLoadItem: (item: HistoryItem) => void;
		onToggleStar: (item: HistoryItem, event?: Event) => void | Promise<void>;
		historyModelSummary: (item: HistoryItem) => string;
		formatHistoryDate: (at: number) => string;
		formatElapsed: (ms: number | null | undefined) => string;
		catalogName: (id: string | null | undefined) => string;
		historyTokenSummary: (item: HistoryItem) => string;
		historyPreviewText: (text: string) => string;
		shortModel: (model: string | null | undefined) => string;
	};

	let {
		historyManagerView,
		historyManagerTab = $bindable('thumbs'),
		historyManagerPage,
		historyManagerLoading,
		historyManagerTotalPages,
		historyManagerOffset,
		historyManagerShownTo,
		managedHistoryItems,
		managedHistoryTotal,
		managerTrashTotal,
		trashTotal,
		selectedHistoryIds,
		historySearch = $bindable(''),
		historyManagerStarredOnly,
		onClose,
		onSetView,
		onSetPage,
		onSetStarredOnly,
		onSelectAll,
		onAskTrash,
		onAskRestore,
		onAskPermanentDelete,
		onToggleSelection,
		onLoadItem,
		onToggleStar,
		historyModelSummary,
		formatHistoryDate,
		formatElapsed,
		catalogName,
		historyTokenSummary,
		historyPreviewText,
		shortModel
	}: Props = $props();

	type TooltipState = {
		item: HistoryItem;
		index: number;
		x: number;
		y: number;
		placement: 'below' | 'above';
	};

	let tooltipState = $state<TooltipState | null>(null);
	let tooltipTimer: ReturnType<typeof setTimeout> | null = null;

	function handleThumbKeydown(event: KeyboardEvent, item: HistoryItem) {
		if (event.key !== 'Enter' && event.key !== ' ') return;
		event.preventDefault();
		if (historyManagerView === 'active') onLoadItem(item);
	}

	function hideTooltip() {
		if (tooltipTimer !== null) {
			clearTimeout(tooltipTimer);
			tooltipTimer = null;
		}
		tooltipState = null;
	}

	function scheduleTooltip(target: HTMLElement, item: HistoryItem, index: number) {
		hideTooltip();
		tooltipTimer = setTimeout(() => {
			const rect = target.getBoundingClientRect();
			const tooltipWidth = 340;
			const tooltipHeight = 150;
			const margin = 14;
			const x = Math.max(
				margin + tooltipWidth / 2,
				Math.min(window.innerWidth - margin - tooltipWidth / 2, rect.left + rect.width / 2)
			);
			const belowY = rect.bottom + 10;
			const fitsBelow = belowY + tooltipHeight <= window.innerHeight - margin;
			tooltipState = {
				item,
				index,
				x,
				y: fitsBelow ? belowY : Math.max(margin, rect.top - 10),
				placement: fitsBelow ? 'below' : 'above',
			};
		}, 700);
	}
</script>

<div class="modal-backdrop" onclick={onClose} aria-hidden="true"></div>
<div class="history-modal" role="dialog" aria-modal="true" tabindex="-1">
	<div class="modal-head">
		<div class="catalog-modal-title">{t().historyManagerTitle}</div>
		<div class="modal-head-actions">
			<button
				class="ghost-btn"
				class:ghost-active={historyManagerView === 'trash'}
				onclick={() => onSetView(historyManagerView === 'trash' ? 'active' : 'trash')}
			>{t().historyTrashButton(managerTrashTotal || trashTotal)}</button>
			<button class="catalog-close" onclick={onClose}>×</button>
		</div>
	</div>
	<div class="settings-tabs history-mode-tabs">
		<button class:active={historyManagerTab === 'thumbs'} onclick={() => (historyManagerTab = 'thumbs')}>{t().historyThumbsTab}</button>
		<button class:active={historyManagerTab === 'list'} onclick={() => (historyManagerTab = 'list')}>{t().historyListTab}</button>
	</div>
	<div class="history-tools">
		<span class="history-manager-count">
			{#if managedHistoryTotal === 0}
				0 / 0
			{:else}
				{historyManagerOffset + 1}-{historyManagerShownTo} / {managedHistoryTotal}
			{/if}
		</span>
		<button class="ghost-btn" onclick={onSelectAll}>{t().historySelectAll}</button>
		<button
			class="ghost-btn"
			class:ghost-active={historyManagerStarredOnly}
			onclick={() => onSetStarredOnly(!historyManagerStarredOnly)}
		>{t().historyStarredOnly}</button>
		{#if historyManagerView === 'active'}
			<button class="ghost-btn" onclick={() => onAskTrash(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyMoveToTrash}</button>
		{:else}
			<button class="ghost-btn" onclick={() => onAskRestore(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyRestoreSelected}</button>
			<button class="danger-btn" onclick={() => onAskPermanentDelete(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyPermanentDelete}</button>
		{/if}
		<label class="history-search">{t().historySearchLabel} <input bind:value={historySearch} /></label>
	</div>
	<div class="history-manager-pager">
		<button class="ghost-btn history-nav-btn" onclick={() => onSetPage(historyManagerPage - 1)} disabled={historyManagerPage <= 0 || historyManagerLoading}>{t().historyPrev}</button>
		<span>{historyManagerLoading ? t().historyLoading : `${historyManagerPage + 1} / ${historyManagerTotalPages}`}</span>
		<button class="ghost-btn history-nav-btn" onclick={() => onSetPage(historyManagerPage + 1)} disabled={historyManagerPage >= historyManagerTotalPages - 1 || historyManagerLoading}>{t().historyNext}</button>
	</div>
	{#if historyManagerTab === 'thumbs'}
		<div class="history-thumb-grid-wrap">
			<div class="history-thumb-grid">
				{#each managedHistoryItems as it, i (it.id ?? it.at)}
					<div class="manager-thumb-wrap" class:selected={!!it.id && selectedHistoryIds.includes(it.id)}>
						<label class="manager-check">
							<input type="checkbox" checked={!!it.id && selectedHistoryIds.includes(it.id)} onchange={() => it.id && onToggleSelection(it.id)} />
						</label>
						<div
							class="thumb manager-thumb"
							onclick={() => historyManagerView === 'active' && onLoadItem(it)}
							onkeydown={(event) => handleThumbKeydown(event, it)}
							onmouseenter={(event) => scheduleTooltip(event.currentTarget as HTMLElement, it, i)}
							onmouseleave={hideTooltip}
							onfocus={(event) => scheduleTooltip(event.currentTarget as HTMLElement, it, i)}
							onblur={hideTooltip}
							role="button"
							tabindex={historyManagerView === 'active' ? 0 : -1}
						>
							<HistoryThumbnail item={it} scope="manager" size="manager" />
							<button
								class="thumb-star"
								class:starred={!!it.starred}
								onclick={(event) => onToggleStar(it, event)}
								title={it.starred ? t().starOn : t().starOff}
								aria-label={it.starred ? t().starOn : t().starOff}
							>★</button>
							<div class="thumb-meta">
								<span class="thumb-time">{formatElapsed(it.elapsed_ms)}</span>
								{#if it.stage2_model}<span class="thumb-model">{shortModel(it.stage2_model)}</span>{/if}
							</div>
						</div>
						<div class="manager-thumb-actions">
							{#if historyManagerView === 'active'}
								<button class="ghost-btn" onclick={() => it.id && onAskTrash([it.id])}>{t().deleteButton}</button>
							{:else}
								<button class="ghost-btn" onclick={() => it.id && onAskRestore([it.id])}>{t().historyRestore}</button>
								<button class="danger-btn" onclick={() => it.id && onAskPermanentDelete([it.id])}>{t().historyPermanentDelete}</button>
							{/if}
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}
		<div class="history-table-wrap">
			<table class="history-table">
				<thead>
					<tr><th></th><th>{t().historyImageHeader}</th><th>{t().historyCreatedAtHeader}</th><th>{t().historyModelHeader}</th><th>{t().historySecondsHeader}</th><th>{t().historyCatalogHeader}</th><th>{t().historyActionHeader}</th></tr>
				</thead>
				<tbody>
					{#each managedHistoryItems as it (it.id ?? it.at)}
						<tr>
							<td><input type="checkbox" checked={!!it.id && selectedHistoryIds.includes(it.id)} onchange={() => it.id && onToggleSelection(it.id)} /></td>
							<td class="table-thumb-cell">
								<HistoryThumbnail item={it} scope="table" size="mini" />
								<button
									class="thumb-star mini-star"
									class:starred={!!it.starred}
									onclick={(event) => onToggleStar(it, event)}
									title={it.starred ? t().starOn : t().starOff}
									aria-label={it.starred ? t().starOn : t().starOff}
								>★</button>
							</td>
							<td>{formatHistoryDate(it.at)}</td>
							<td>{historyModelSummary(it)}</td>
							<td>{formatElapsed(it.elapsed_ms)}</td>
							<td>{catalogName(it.catalog_id)}</td>
							<td>
								{#if historyManagerView === 'active'}
									<button class="ghost-btn" onclick={() => it.id && onAskTrash([it.id])}>{t().deleteButton}</button>
								{:else}
									<button class="ghost-btn" onclick={() => it.id && onAskRestore([it.id])}>{t().historyRestore}</button>
									<button class="danger-btn" onclick={() => it.id && onAskPermanentDelete([it.id])}>{t().historyPermanentDelete}</button>
								{/if}
							</td>
						</tr>
					{/each}
				</tbody>
			</table>
		</div>
	{/if}
</div>
{#if tooltipState}
	<div
		class="manager-tooltip"
		class:above={tooltipState.placement === 'above'}
		style="left: {tooltipState.x}px; top: {tooltipState.y}px;"
	>
		<div class="tooltip-title">#{historyManagerOffset + tooltipState.index + 1}</div>
		<div class="tooltip-row"><span>{t().historyTooltipModel}</span><strong>{historyModelSummary(tooltipState.item)}</strong></div>
		<div class="tooltip-row"><span>{t().historyTooltipSavedAt}</span><strong>{formatHistoryDate(tooltipState.item.at)}</strong></div>
		<div class="tooltip-row"><span>{t().historyTooltipSeconds}</span><strong>{formatElapsed(tooltipState.item.elapsed_ms)}</strong></div>
		<div class="tooltip-row"><span>{t().historyTooltipColorCatalog}</span><strong>{catalogName(tooltipState.item.catalog_id)}</strong></div>
		<div class="tooltip-row"><span>{t().historyTooltipTokens}</span><strong>{historyTokenSummary(tooltipState.item)}</strong></div>
		<div class="tooltip-date">{historyPreviewText(tooltipState.item.input)}</div>
	</div>
{/if}

<style>
	.modal-backdrop {
		position: fixed;
		inset: 0;
		z-index: 400;
		background: rgba(0,0,0,0.25);
		backdrop-filter: blur(2px);
	}
	.history-modal {
		position: fixed;
		top: 50%;
		left: 50%;
		transform: translate(-50%, -50%);
		z-index: 401;
		background: var(--panel2);
		border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		width: min(1240px, calc(100vw - 24px));
		height: min(720px, calc(100vh - 32px));
		max-height: 88vh;
	}
	.modal-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		padding: 14px 18px 10px;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}
	.catalog-modal-title { font-size: 15px; font-weight: 300; letter-spacing: 0.05em; }
	.catalog-close {
		width: 24px;
		height: 24px;
		border: none;
		background: none;
		color: var(--fg3);
		font-size: 18px;
		cursor: pointer;
		line-height: 1;
	}
	.modal-head-actions { display: flex; align-items: center; gap: 8px; }
	.settings-tabs {
		display: flex;
		gap: 0;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
	}
	.settings-tabs button {
		padding: 9px 16px;
		border: none;
		border-bottom: 2px solid transparent;
		background: none;
		color: var(--fg2);
		font-size: 13px;
		cursor: pointer;
		font-family: inherit;
	}
	.settings-tabs button.active { color: var(--fg); border-bottom-color: var(--fg); font-weight: 500; }
	.history-tools {
		display: flex;
		align-items: center;
		gap: 8px;
		padding: 10px 14px;
		border-bottom: 1px solid var(--border);
		flex-wrap: wrap;
	}
	.history-mode-tabs { flex-shrink: 0; }
	.history-manager-count {
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		margin-right: 2px;
	}
	.history-search {
		margin-left: auto;
		display: flex;
		align-items: center;
		gap: 6px;
		color: var(--fg2);
		font-size: 12px;
	}
	.history-search input {
		width: min(240px, 30vw);
		flex: 1;
		min-width: 0;
		padding: 5px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font-size: 12px;
		font-family: inherit;
	}
	.history-manager-pager {
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 10px;
		padding: 8px 14px;
		border-bottom: 1px solid var(--border);
		color: var(--fg3);
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.history-nav-btn { min-width: 92px; }
	.history-thumb-grid-wrap,
	.history-table-wrap {
		flex: 1;
		overflow: auto;
		padding: 12px 14px 14px;
		min-height: 0;
	}
	.history-thumb-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
		gap: 12px;
		align-items: start;
	}
	.manager-thumb-wrap {
		position: relative;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		padding: 7px;
		transition: border-color 0.12s, box-shadow 0.12s;
	}
	.manager-thumb-wrap.selected {
		border-color: var(--accent);
		box-shadow: 0 0 0 2px var(--accent-light);
	}
	.manager-check {
		position: absolute;
		top: 6px;
		left: 6px;
		z-index: 30;
		background: rgba(255,255,255,0.86);
		border-radius: 3px;
		line-height: 1;
		padding: 2px;
	}
	.thumb-star {
		position: absolute;
		top: 5px;
		right: 5px;
		z-index: 31;
		width: 22px;
		height: 22px;
		border: 1px solid rgba(0,0,0,0.12);
		border-radius: 50%;
		background: rgba(255,255,255,0.88);
		color: rgba(40,36,30,0.42);
		font-size: 14px;
		line-height: 1;
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.thumb-star.starred { color: #d59b21; background: #fff6ce; border-color: rgba(213,155,33,0.45); }
	.table-thumb-cell { position: relative; width: 66px; }
	.table-thumb-cell .mini-star {
		top: 2px;
		right: 2px;
		width: 18px;
		height: 18px;
		font-size: 11px;
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
	.manager-tooltip {
		position: fixed;
		transform: translateX(-50%);
		pointer-events: none;
		background: var(--panel);
		color: var(--fg);
		font-size: 11px;
		border-radius: var(--r);
		border: 1px solid var(--border2);
		padding: 9px 11px;
		text-align: left;
		width: min(340px, calc(100vw - 28px));
		z-index: 5000;
		line-height: 1.7;
		box-shadow: 0 12px 36px rgba(0,0,0,0.22);
	}
	.manager-tooltip.above {
		transform: translateX(-50%) translateY(-100%);
	}
	.tooltip-title { font-weight: 500; margin-bottom: 3px; }
	.tooltip-row {
		display: grid;
		grid-template-columns: 70px minmax(0, 1fr);
		gap: 8px;
		align-items: baseline;
	}
	.tooltip-row span { color: var(--fg3); }
	.tooltip-row strong {
		font-weight: 500;
		color: var(--fg);
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.tooltip-date {
		color: var(--fg2);
		margin-top: 3px;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
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
	.manager-thumb {
		width: 100%;
	}
	.manager-thumb-actions {
		display: flex;
		gap: 5px;
		margin-top: 7px;
		flex-wrap: wrap;
	}
	.manager-thumb-actions .ghost-btn,
	.manager-thumb-actions .danger-btn {
		font-size: 10px;
		padding: 3px 7px;
	}
	.history-table {
		width: 100%;
		border-collapse: collapse;
		background: var(--panel);
		font-size: 12px;
	}
	.history-table th,
	.history-table td {
		border: 1px solid var(--border);
		padding: 7px 8px;
		text-align: left;
		vertical-align: middle;
	}
	.history-table th { color: var(--fg3); font-weight: 500; background: var(--bg); }
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
	.ghost-btn.ghost-active { background: var(--fg); color: #fff; border-color: var(--fg); }
	.danger-btn {
		padding: 4px 10px;
		border: none;
		border-radius: var(--r);
		background: #c0392b;
		color: #fff;
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.danger-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
