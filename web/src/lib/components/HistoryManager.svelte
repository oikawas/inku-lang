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
		onClose: () => void;
		onSetView: (view: 'active' | 'trash') => void;
		onSetPage: (page: number) => void;
		onSelectAll: () => void;
		onAskTrash: (ids: string[]) => void;
		onAskRestore: (ids: string[]) => void;
		onAskPermanentDelete: (ids: string[]) => void;
		onToggleSelection: (id: string) => void;
		onLoadItem: (item: HistoryItem) => void;
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
		onClose,
		onSetView,
		onSetPage,
		onSelectAll,
		onAskTrash,
		onAskRestore,
		onAskPermanentDelete,
		onToggleSelection,
		onLoadItem,
		historyModelSummary,
		formatHistoryDate,
		formatElapsed,
		catalogName,
		historyTokenSummary,
		historyPreviewText,
		shortModel
	}: Props = $props();
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
						<button class="thumb manager-thumb" onclick={() => historyManagerView === 'active' && onLoadItem(it)}>
							<div class="thumb-tooltip">
								<div class="tooltip-title">#{historyManagerOffset + i + 1}</div>
								<div>{t().historyTooltipModel}: {historyModelSummary(it)}</div>
								<div>{t().historyTooltipSavedAt}: {formatHistoryDate(it.at)}</div>
								<div>{t().historyTooltipSeconds}: {formatElapsed(it.elapsed_ms)}</div>
								<div>{t().historyTooltipColorCatalog}: {catalogName(it.catalog_id)}</div>
								<div>{t().historyTooltipTokens}: {historyTokenSummary(it)}</div>
								<div class="tooltip-date">{historyPreviewText(it.input)}</div>
							</div>
							<HistoryThumbnail item={it} scope="manager" size="manager" />
							<div class="thumb-meta">
								<span class="thumb-time">{formatElapsed(it.elapsed_ms)}</span>
								{#if it.stage2_model}<span class="thumb-model">{shortModel(it.stage2_model)}</span>{/if}
							</div>
						</button>
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
							<td><HistoryThumbnail item={it} scope="table" size="mini" /></td>
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
		background: #faf9f6;
		border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		width: min(920px, calc(100vw - 32px));
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
		background: #fff;
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
		background: #fff;
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
	.tooltip-date { color: rgba(255,255,255,0.55); margin-top: 3px; }
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
		background: #fff;
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
		background: #fff;
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
