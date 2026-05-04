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
		render_hash?: string | null;
		render_hash_short?: string | null;
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
		onSetPageSize: (pageSize: number) => void;
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
		onSetPageSize,
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
	let thumbGridWrapEl = $state<HTMLDivElement | null>(null);

	function loadItemAndClose(item: HistoryItem) {
		if (historyManagerView !== 'active') return;
		hideTooltip();
		onLoadItem(item);
		onClose();
	}

	function handleThumbKeydown(event: KeyboardEvent, item: HistoryItem) {
		if (event.key !== 'Enter' && event.key !== ' ') return;
		event.preventDefault();
		loadItemAndClose(item);
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
			const tooltipWidth = Math.min(440, window.innerWidth - 28);
			const tooltipHeight = 430;
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

	function hashLabel(item: HistoryItem): string {
		return (item.render_hash_short || item.render_hash?.slice(-4) || '').toUpperCase();
	}

	function copyHash(item: HistoryItem, event: MouseEvent) {
		event.stopPropagation();
		event.preventDefault();
		const hash = item.render_hash || hashLabel(item);
		if (!hash) return;
		if (navigator.clipboard?.writeText) {
			void navigator.clipboard.writeText(hash).catch(() => fallbackCopy(hash));
			return;
		}
		fallbackCopy(hash);
	}

	function fallbackCopy(text: string) {
		const textarea = document.createElement('textarea');
		textarea.value = text;
		textarea.setAttribute('readonly', '');
		textarea.style.position = 'fixed';
		textarea.style.left = '-9999px';
		textarea.style.top = '0';
		document.body.appendChild(textarea);
		textarea.select();
		try {
			document.execCommand('copy');
		} finally {
			document.body.removeChild(textarea);
		}
	}

	function thumbnailPromptText(text: string): string {
		return historyPreviewText(text.replace(/^\s*#\d+\s*/, ''));
	}

	function toggleStarFromThumb(item: HistoryItem, event: MouseEvent) {
		event.preventDefault();
		event.stopPropagation();
		void onToggleStar(item, event);
	}

	function calculatePageSize(element: HTMLElement): number {
		const width = element.clientWidth;
		const height = element.clientHeight;
		if (width <= 0 || height <= 0) return 1;
		const grid = element.querySelector('.history-thumb-grid');
		const computed = grid ? getComputedStyle(grid) : null;
		const gap = computed ? Number.parseFloat(computed.rowGap || computed.gap || '8') || 8 : 8;
		const minCardWidth = 104;
		const columns = Math.max(1, Math.floor((width + gap) / (minCardWidth + gap)));
		const firstCard = element.querySelector('.manager-thumb-wrap');
		let cardHeight = firstCard instanceof HTMLElement ? firstCard.getBoundingClientRect().height : 0;
		if (cardHeight <= 0) {
			const cardWidth = Math.max(minCardWidth, (width - gap * (columns - 1)) / columns);
			const imageHeight = cardWidth * 58 / 82;
			cardHeight = imageHeight + 48;
		}
		const rows = Math.max(1, Math.floor((height + gap) / (cardHeight + gap)));
		return Math.max(1, columns * rows);
	}

	$effect(() => {
		const element = thumbGridWrapEl;
		managedHistoryItems.length;
		if (!element || historyManagerTab !== 'thumbs') return;
		let frame = 0;
		const update = () => {
			cancelAnimationFrame(frame);
			frame = requestAnimationFrame(() => onSetPageSize(calculatePageSize(element)));
		};
		update();
		const observer = new ResizeObserver(update);
		observer.observe(element);
		return () => {
			cancelAnimationFrame(frame);
			observer.disconnect();
		};
	});
</script>

<div class="modal-backdrop" onclick={onClose} aria-hidden="true"></div>
<div class="history-modal" role="dialog" aria-modal="true" tabindex="-1">
	<div class="modal-head">
		<div class="history-head-left">
			<div class="catalog-modal-title">{t().historyManagerTitle}</div>
			<div class="settings-tabs history-mode-tabs">
				<button class:active={historyManagerTab === 'thumbs'} onclick={() => (historyManagerTab = 'thumbs')}>{t().historyThumbsTab}</button>
				<button class:active={historyManagerTab === 'list'} onclick={() => (historyManagerTab = 'list')}>{t().historyListTab}</button>
			</div>
			<span class="history-manager-count">
				{#if managedHistoryTotal === 0}
					0 / 0
				{:else}
					{historyManagerOffset + 1}-{historyManagerShownTo} / {managedHistoryTotal}
				{/if}
			</span>
		</div>
		<div class="history-head-actions">
			<div class="history-manager-pager">
				<button class="ghost-btn history-nav-btn" onclick={() => onSetPage(historyManagerPage - 1)} disabled={historyManagerPage <= 0 || historyManagerLoading}>{t().historyPrev}</button>
				<span>{historyManagerLoading ? t().historyLoading : `${historyManagerPage + 1} / ${historyManagerTotalPages}`}</span>
				<button class="ghost-btn history-nav-btn" onclick={() => onSetPage(historyManagerPage + 1)} disabled={historyManagerPage >= historyManagerTotalPages - 1 || historyManagerLoading}>{t().historyNext}</button>
			</div>
			<button class="catalog-close" onclick={onClose}>×</button>
		</div>
	</div>
	<div class="history-tools">
		<div class="history-tool-group">
			<button class="ghost-btn" onclick={onSelectAll}>{t().historySelectAll}</button>
			<button
				class="ghost-btn"
				class:ghost-active={historyManagerStarredOnly}
				onclick={() => onSetStarredOnly(!historyManagerStarredOnly)}
			>{t().historyStarredOnly}</button>
			<button
				class="ghost-btn"
				class:ghost-active={historyManagerView === 'trash'}
				onclick={() => onSetView(historyManagerView === 'trash' ? 'active' : 'trash')}
			>{t().historyTrashButton(managerTrashTotal || trashTotal)}</button>
			{#if historyManagerView === 'active'}
				<button class="ghost-btn" onclick={() => onAskTrash(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyMoveToTrash}</button>
			{:else}
				<button class="ghost-btn" onclick={() => onAskRestore(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyRestoreSelected}</button>
				<button class="danger-btn" onclick={() => onAskPermanentDelete(selectedHistoryIds)} disabled={selectedHistoryIds.length === 0}>{t().historyPermanentDelete}</button>
			{/if}
		</div>
		<label class="history-search">{t().historySearchLabel} <input bind:value={historySearch} /></label>
	</div>
	{#if historyManagerTab === 'thumbs'}
		<div class="history-thumb-grid-wrap" bind:this={thumbGridWrapEl}>
			<div class="history-thumb-grid">
				{#each managedHistoryItems as it, i (it.id ?? it.at)}
					<div class="manager-thumb-wrap" class:selected={!!it.id && selectedHistoryIds.includes(it.id)}>
						<label class="manager-check">
							<input type="checkbox" checked={!!it.id && selectedHistoryIds.includes(it.id)} onchange={() => it.id && onToggleSelection(it.id)} />
						</label>
						<div
							class="thumb manager-thumb"
							onclick={() => loadItemAndClose(it)}
							onkeydown={(event) => handleThumbKeydown(event, it)}
							onmouseenter={(event) => scheduleTooltip(event.currentTarget as HTMLElement, it, i)}
							onmouseleave={hideTooltip}
							onfocus={(event) => scheduleTooltip(event.currentTarget as HTMLElement, it, i)}
							onblur={hideTooltip}
							role="button"
							tabindex={historyManagerView === 'active' ? 0 : -1}
						>
							<HistoryThumbnail item={it} scope="manager" size="manager" />
						</div>
						<div class="manager-thumb-actions">
							<div class="thumb-catalog" title={it.input}>{thumbnailPromptText(it.input)}</div>
							<div class="thumb-action-row">
								<button
									class="hash-row-star"
									class:starred={!!it.starred}
									onclick={(event) => toggleStarFromThumb(it, event)}
									title={it.starred ? t().starOn : t().starOff}
									aria-label={it.starred ? t().starOn : t().starOff}
								>★</button>
								{#if hashLabel(it)}<button class="hash-chip" onclick={(event) => copyHash(it, event)} title={t().historyHashCopyTitle}>{hashLabel(it)}</button>{/if}
								{#if historyManagerView === 'active'}
									<button class="ghost-btn icon-trash-btn" onclick={() => it.id && onAskTrash([it.id])} title={t().deleteButton} aria-label={t().deleteButton}>
										<svg viewBox="2 2 20 20" aria-hidden="true">
											<path d="M3 6h18" />
											<path d="M8 6V4h8v2" />
											<path d="M6 6l1 15h10l1-15" />
											<path d="M10 10v7" />
											<path d="M14 10v7" />
										</svg>
									</button>
								{:else}
									<button class="ghost-btn" onclick={() => it.id && onAskRestore([it.id])}>{t().historyRestore}</button>
									<button class="danger-btn" onclick={() => it.id && onAskPermanentDelete([it.id])}>{t().historyPermanentDelete}</button>
								{/if}
							</div>
						</div>
					</div>
				{/each}
			</div>
		</div>
	{:else}
		<div class="history-table-wrap">
			<table class="history-table">
				<thead>
					<tr><th></th><th>{t().historyImageHeader}</th><th>{t().historyHashHeader}</th><th>{t().historyCreatedAtHeader}</th><th>{t().historyModelHeader}</th><th>{t().historySecondsHeader}</th><th>{t().historyCatalogHeader}</th><th>{t().historyActionHeader}</th></tr>
				</thead>
				<tbody>
					{#each managedHistoryItems as it (it.id ?? it.at)}
						<tr>
							<td><input type="checkbox" checked={!!it.id && selectedHistoryIds.includes(it.id)} onchange={() => it.id && onToggleSelection(it.id)} /></td>
							<td class="table-thumb-cell">
								<button
									class="table-thumb-select"
									onclick={() => loadItemAndClose(it)}
									disabled={historyManagerView !== 'active'}
									title={t().historyImageHeader}
									aria-label={t().historyImageHeader}
								>
									<HistoryThumbnail item={it} scope="table" size="mini" />
								</button>
								<button
									class="thumb-star mini-star"
									class:starred={!!it.starred}
									onclick={(event) => onToggleStar(it, event)}
									title={it.starred ? t().starOn : t().starOff}
									aria-label={it.starred ? t().starOn : t().starOff}
								>★</button>
							</td>
							<td>{#if hashLabel(it)}<button class="hash-chip table-hash" onclick={(event) => copyHash(it, event)} title={t().historyHashCopyTitle}>#{hashLabel(it)}</button>{/if}</td>
							<td>{formatHistoryDate(it.at)}</td>
							<td>{historyModelSummary(it)}</td>
							<td>{formatElapsed(it.elapsed_ms)}</td>
							<td>{catalogName(it.catalog_id)}</td>
							<td>
								{#if historyManagerView === 'active'}
									<button class="ghost-btn icon-trash-btn" onclick={() => it.id && onAskTrash([it.id])} title={t().deleteButton} aria-label={t().deleteButton}>
										<svg viewBox="2 2 20 20" aria-hidden="true">
											<path d="M3 6h18" />
											<path d="M8 6V4h8v2" />
											<path d="M6 6l1 15h10l1-15" />
											<path d="M10 10v7" />
											<path d="M14 10v7" />
										</svg>
									</button>
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
		<div class="tooltip-preview">
			<HistoryThumbnail item={tooltipState.item} scope="tooltip" size="manager" />
		</div>
		<div class="tooltip-title">#{historyManagerOffset + tooltipState.index + 1}</div>
		<div class="tooltip-row"><span>{t().historyTooltipModel}</span><strong>{historyModelSummary(tooltipState.item)}</strong></div>
		<div class="tooltip-row"><span>{t().historyTooltipSavedAt}</span><strong>{formatHistoryDate(tooltipState.item.at)}</strong></div>
		<div class="tooltip-row"><span>{t().historyTooltipSeconds}</span><strong>{formatElapsed(tooltipState.item.elapsed_ms)}</strong></div>
		<div class="tooltip-row"><span>{t().historyTooltipColorCatalog}</span><strong>{catalogName(tooltipState.item.catalog_id)}</strong></div>
		{#if hashLabel(tooltipState.item)}<div class="tooltip-row"><span>{t().historyHashHeader}</span><strong>#{hashLabel(tooltipState.item)}</strong></div>{/if}
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
		top: 10vh;
		left: 10vw;
		z-index: 401;
		background: var(--panel2);
		border-radius: var(--r-lg);
		box-shadow: 0 12px 48px rgba(0,0,0,0.18);
		display: flex;
		flex-direction: column;
		overflow: hidden;
		width: 80vw;
		height: 80vh;
	}
	.modal-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 9px 12px;
		border-bottom: 1px solid var(--border);
		flex-shrink: 0;
	}
	.history-head-left,
	.history-head-actions,
	.history-tool-group {
		display: flex;
		align-items: center;
		gap: 8px;
		min-width: 0;
	}
	.history-head-left { flex: 1 1 auto; }
	.history-head-actions { flex: 0 0 auto; }
	.catalog-modal-title {
		flex: 0 0 auto;
		font-size: 15px;
		font-weight: 300;
		letter-spacing: 0.05em;
	}
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
	.settings-tabs {
		display: flex;
		gap: 0;
		background: var(--bg);
		border: 1px solid var(--border);
		border-radius: var(--r);
		overflow: hidden;
	}
	.settings-tabs button {
		padding: 4px 9px;
		border: none;
		background: none;
		color: var(--fg2);
		font-size: 11px;
		cursor: pointer;
		font-family: inherit;
	}
	.settings-tabs button + button { border-left: 1px solid var(--border); }
	.settings-tabs button.active { color: var(--fg); background: var(--panel); font-weight: 500; }
	.history-tools {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 10px;
		padding: 7px 12px;
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
		gap: 6px;
		color: var(--fg3);
		font-size: 11px;
		font-variant-numeric: tabular-nums;
	}
	.history-nav-btn { min-width: 74px; }
	.history-thumb-grid-wrap,
	.history-table-wrap {
		flex: 1;
		padding: 8px 10px 6px;
		min-height: 0;
	}
	.history-thumb-grid-wrap { overflow: hidden; }
	.history-table-wrap { overflow: auto; }
	.history-thumb-grid {
		display: grid;
		grid-template-columns: repeat(auto-fill, minmax(104px, 1fr));
		gap: 8px;
		align-items: start;
	}
	.manager-thumb-wrap {
		position: relative;
		border: 1px solid var(--border);
		border-radius: var(--r);
		background: var(--panel);
		padding: 5px;
		transition: border-color 0.12s, box-shadow 0.12s;
		content-visibility: auto;
		contain-intrinsic-size: 150px 164px;
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
		border-radius: 2px;
		line-height: 1;
		padding: 1px;
	}
	.manager-check input {
		width: 12px;
		height: 12px;
		margin: 0;
		accent-color: var(--accent);
		outline: 0.5px solid rgba(40,36,30,0.32);
		outline-offset: -1px;
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
	.table-thumb-select {
		display: block;
		width: 48px;
		height: 48px;
		padding: 0;
		border: 0;
		background: transparent;
		cursor: pointer;
	}
	.table-thumb-select:disabled { cursor: default; }
	.table-thumb-cell :global(svg) {
		content-visibility: auto;
		contain-intrinsic-size: 48px 48px;
	}
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
		width: min(440px, calc(100vw - 28px));
		z-index: 5000;
		line-height: 1.7;
		box-shadow: 0 12px 36px rgba(0,0,0,0.22);
	}
	.manager-tooltip.above {
		transform: translateX(-50%) translateY(-100%);
	}
	.tooltip-title { font-weight: 500; margin-bottom: 3px; }
	.tooltip-preview {
		width: 100%;
		max-height: min(300px, 48vh);
		margin-bottom: 8px;
		border: 1px solid var(--border);
		border-radius: var(--r);
		overflow: hidden;
		background: var(--panel);
	}
	.tooltip-preview :global(.history-thumbnail.manager) {
		width: 100%;
		height: auto;
	}
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
	.thumb-catalog {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
		color: var(--fg2);
		font-size: 11px;
		line-height: 1.25;
	}
	.thumb-action-row {
		display: flex;
		align-items: flex-end;
		gap: 4px;
		justify-content: flex-start;
		min-width: 0;
		position: relative;
		z-index: 40;
	}
	.hash-row-star {
		flex: 0 0 auto;
		position: relative;
		z-index: 41;
		width: 18px;
		height: 18px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		background: var(--panel);
		color: var(--fg3);
		font-size: 10px;
		line-height: 1;
		cursor: pointer;
		pointer-events: auto;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
	}
	.hash-row-star.starred {
		color: #d59b21;
		background: #fff6ce;
		border-color: rgba(213,155,33,0.45);
	}
	:global(html[data-theme='dark']) .hash-row-star {
		color: #b8c0cc;
		border-color: rgba(255,255,255,0.22);
		background: rgba(255,255,255,0.06);
	}
	:global(html[data-theme='dark']) .hash-row-star.starred {
		color: #ffd166;
		background: rgba(213,155,33,0.18);
		border-color: rgba(255,209,102,0.55);
	}
	.hash-chip {
		align-self: flex-end;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-family: inherit;
		font-size: 10px;
		line-height: 1;
		padding: 3px 7px;
		cursor: copy;
	}
	.hash-chip:hover {
		border-color: var(--accent);
		color: var(--fg);
	}
	.table-hash {
		font-size: 11px;
		white-space: nowrap;
	}
	.manager-thumb {
		width: 100%;
	}
	.manager-thumb-actions {
		display: flex;
		flex-direction: column;
		gap: 4px;
		margin-top: 5px;
		min-width: 0;
		position: relative;
		z-index: 40;
	}
	.manager-thumb-actions .ghost-btn,
	.manager-thumb-actions .danger-btn {
		flex: 0 0 auto;
		margin-left: auto;
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
	.icon-trash-btn {
		width: 24px;
		height: 22px;
		padding: 0;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		color: var(--fg2);
	}
	.icon-trash-btn svg {
		width: 22px;
		height: 20px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.7;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.icon-trash-btn:hover { color: var(--fg); }
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
