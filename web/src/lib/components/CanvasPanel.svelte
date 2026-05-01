<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import OutputTabsContent from './OutputTabsContent.svelte';

	type OutputTab = 'canvas' | 'prompts' | 'score';
	type PaintResult = { svg: string; score: { instructions: unknown[] } };
	type PromptsData = { stage1_system: string; stage2_system: string };
	type HistoryItem = { id?: string; starred?: boolean };

	type Props = {
		outputTab: OutputTab;
		result: PaintResult | null;
		allowEmptyOutputTabs: boolean;
		currentRenderedAt: string | null;
		nextDisabled: boolean;
		prevDisabled: boolean;
		historyTotal: number;
		navPos: number;
		zoom: number;
		actualZoom: number;
		canPan: boolean;
		panX: number;
		panY: number;
		canvasDragging: boolean;
		promptsData: PromptsData | null;
		stage1PromptText: string;
		ddl: string | null;
		promptStage1Expanded: boolean;
		promptStage2Expanded: boolean;
		copiedPrompt: 'stage1' | 'stage2' | null;
		scoreJsonLines: string[];
		scoreJsonHighlighted: string;
		statusStage1Model: string;
		statusStage2Model: string;
		statusCatalogName: string;
		statusHistoryItem: HistoryItem | null;
		pngMenuOpen: boolean;
		pngWrapEl: HTMLDivElement | null;
		onGotoNext: () => void | Promise<void>;
		onGotoPrev: () => void | Promise<void>;
		onPointerDown: (event: PointerEvent) => void;
		onPointerMove: (event: PointerEvent) => void;
		onPointerUp: (event: PointerEvent) => void;
		onSetZoom: (zoom: number) => void;
		onResetZoom: () => void;
		onFitZoomChange: (zoom: number) => void;
		onCopyPromptText: (kind: 'stage1' | 'stage2', text: string | null | undefined) => void | Promise<void>;
		onToggleStar: (item: HistoryItem | null | undefined, event?: Event) => void | Promise<void>;
		onDownloadSVG: () => void;
		onDownloadPNG: (size: number) => void | Promise<void>;
	};

	let {
		outputTab = $bindable('canvas'),
		result,
		allowEmptyOutputTabs,
		currentRenderedAt,
		nextDisabled,
		prevDisabled,
		historyTotal,
		navPos,
		zoom,
		actualZoom,
		canPan,
		panX,
		panY,
		canvasDragging,
		promptsData,
		stage1PromptText,
		ddl,
		promptStage1Expanded = $bindable(false),
		promptStage2Expanded = $bindable(false),
		copiedPrompt,
		scoreJsonLines,
		scoreJsonHighlighted,
		statusStage1Model,
		statusStage2Model,
		statusCatalogName,
		statusHistoryItem,
		pngMenuOpen = $bindable(false),
		pngWrapEl = $bindable(null),
		onGotoNext,
		onGotoPrev,
		onPointerDown,
		onPointerMove,
		onPointerUp,
		onSetZoom,
		onResetZoom,
		onFitZoomChange,
		onCopyPromptText,
		onToggleStar,
		onDownloadSVG,
		onDownloadPNG
	}: Props = $props();

	let canvasContentEl: HTMLDivElement | null = null;

	function updateFitZoom() {
		if (!canvasContentEl) return;
		const rect = canvasContentEl.getBoundingClientRect();
		const availableWidth = Math.max(120, rect.width - 120);
		const availableHeight = Math.max(120, rect.height - 96);
		const nextZoom = Math.max(0.25, Math.min(10, Math.min(availableWidth, availableHeight) / 400));
		onFitZoomChange(+nextZoom.toFixed(2));
	}

	onMount(() => {
		updateFitZoom();
		const observer = new ResizeObserver(updateFitZoom);
		if (canvasContentEl) observer.observe(canvasContentEl);
		return () => observer.disconnect();
	});
</script>

<div class="right-panel">
	<div class="right-tabs">
		<button class="rtab" class:active={outputTab === 'canvas'} onclick={() => (outputTab = 'canvas')}>{t().tabCanvas}</button>
		<button class="rtab" class:active={outputTab === 'prompts'} onclick={() => (outputTab = 'prompts')} disabled={!result && !allowEmptyOutputTabs}>{t().tabPrompts}</button>
		<button class="rtab" class:active={outputTab === 'score'} onclick={() => (outputTab = 'score')} disabled={!result && !allowEmptyOutputTabs}>{t().tabScore}</button>
		<div class="rtab-spacer"></div>
		{#if currentRenderedAt}
			<span class="rendered-at">{currentRenderedAt}</span>
		{/if}
	</div>

	<div class="canvas-area">
		<div class="nav-left">
			<button class="nav-circle" onclick={onGotoNext} disabled={nextDisabled}>‹</button>
		</div>

		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div
			bind:this={canvasContentEl}
			class="canvas-content"
			class:can-pan={outputTab === 'canvas' && canPan}
			class:dragging={canvasDragging}
			class:side-nav-safe={outputTab !== 'canvas'}
			onpointerdown={onPointerDown}
			onpointermove={onPointerMove}
			onpointerup={onPointerUp}
			onpointercancel={onPointerUp}
		>
			{#if outputTab === 'canvas'}
				<div class="canvas-pan" style="transform: translate3d({panX}px, {panY}px, 0);">
					<div
						class="canvas-box"
						style="transform: scale({actualZoom}); transform-origin: center center; transition: transform 0.15s;"
					>
						{#if result}
							{@html result.svg}
						{:else}
							<div class="canvas-placeholder-art" aria-label={t().canvasPlaceholder}>
								<svg viewBox="0 0 960 540" role="img">
									<rect x="0" y="0" width="960" height="540" rx="6" fill="#fffdf8" />
									<g opacity="0.72">
										<path d="M158 364 C250 282 338 420 442 328 S624 214 792 312" fill="none" stroke="#cfc6b6" stroke-width="7" stroke-linecap="round" />
										<path d="M168 206 C250 174 318 226 394 200 C474 172 542 118 638 152 C700 174 750 210 814 192" fill="none" stroke="#ded6c9" stroke-width="4" stroke-linecap="round" stroke-dasharray="18 18" />
										<circle cx="312" cy="284" r="34" fill="none" stroke="#d8cfc0" stroke-width="6" />
										<rect x="604" y="260" width="88" height="58" rx="2" fill="none" stroke="#d8cfc0" stroke-width="6" transform="rotate(-12 648 289)" />
										<path d="M472 218 L522 306 L422 306 Z" fill="none" stroke="#d8cfc0" stroke-width="6" stroke-linejoin="round" />
									</g>
								</svg>
							</div>
						{/if}
					</div>
				</div>
			{:else if outputTab === 'prompts'}
				<OutputTabsContent
					outputTab="prompts"
					{promptsData}
					{stage1PromptText}
					{ddl}
					bind:promptStage1Expanded
					bind:promptStage2Expanded
					{copiedPrompt}
					{scoreJsonLines}
					{scoreJsonHighlighted}
					{onCopyPromptText}
				/>
			{:else if outputTab === 'score'}
				<OutputTabsContent
					outputTab="score"
					{promptsData}
					{stage1PromptText}
					{ddl}
					bind:promptStage1Expanded
					bind:promptStage2Expanded
					{copiedPrompt}
					{scoreJsonLines}
					{scoreJsonHighlighted}
					{onCopyPromptText}
				/>
			{/if}
		</div>

		{#if outputTab === 'canvas'}
			<div class="zoom-controls">
				<button onclick={() => onSetZoom(zoom - 0.25)}>−</button>
				<span class="zoom-pct">{Math.round(zoom * 100)}%</span>
				<button onclick={() => onSetZoom(zoom + 0.25)}>＋</button>
				<button class="zoom-reset" onclick={onResetZoom}>⊙</button>
			</div>
		{/if}

		<div class="nav-right">
			<button class="nav-circle" onclick={onGotoPrev} disabled={prevDisabled}>›</button>
			{#if historyTotal > 0}
				<span class="nav-counter">{navPos} / {historyTotal}</span>
			{/if}
		</div>
	</div>

	<div class="status-bar">
		<div class="status-summary" aria-label="current render status">
			<span class="status-group">
				<span class="status-label">LLM</span>
				<span class="status-k">Stage1</span><span class="status-v">{statusStage1Model}</span>
				<span class="status-k">Stage2</span><span class="status-v">{statusStage2Model}</span>
			</span>
			<span class="status-divider"></span>
			<span class="status-group">
				<span class="status-label">Color</span>
				<span class="status-v">{statusCatalogName}</span>
			</span>
		</div>
		<button
			class="star-btn status-star"
			class:starred={!!statusHistoryItem?.starred}
			disabled={!statusHistoryItem?.id}
			onclick={(event) => onToggleStar(statusHistoryItem, event)}
			title={statusHistoryItem?.starred ? t().starOn : t().starOff}
			aria-label={statusHistoryItem?.starred ? t().starOn : t().starOff}
		>★</button>
		<span class="status-export-label">{t().exportLabel}:</span>
		<button class="ghost-btn" onclick={onDownloadSVG} disabled={!result}>↓ SVG</button>
		<div class="png-wrap" bind:this={pngWrapEl}>
			<button class="ghost-btn" onclick={(e) => { e.stopPropagation(); pngMenuOpen = !pngMenuOpen; }} disabled={!result}>↓ PNG ▾</button>
			{#if pngMenuOpen}
				<div class="png-menu">
					{#each [[1080,t().pngStandard],[2160,t().pngHighRes],[1024,t().pngSquare],[2048,t().pngSquareHighRes]] as [size, label]}
						<button onclick={() => { onDownloadPNG(size as number); pngMenuOpen = false; }}>
							<span class="png-size">PNG {size}px</span>
							<span class="png-sub">{label}</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

<style>
	.right-panel {
		flex: 1;
		min-width: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
	}
	.right-tabs {
		display: flex;
		align-items: center;
		border-bottom: 1px solid var(--border);
		background: var(--bg);
		padding: 0 16px;
		flex-shrink: 0;
	}
	.rtab {
		padding: 9px 16px;
		border: none;
		border-bottom: 2px solid transparent;
		background: none;
		color: var(--fg2);
		font-size: 13px;
		cursor: pointer;
		font-family: inherit;
		white-space: nowrap;
	}
	.rtab.active { border-bottom-color: var(--fg); color: var(--fg); font-weight: 500; }
	.rtab:hover:not(.active):not(:disabled) { color: var(--fg); }
	.rtab:disabled { opacity: 0.35; cursor: not-allowed; }
	.rtab-spacer { flex: 1; }
	.rendered-at { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.canvas-area {
		flex: 1;
		display: flex;
		align-items: center;
		justify-content: center;
		background: var(--bg2);
		position: relative;
		overflow: hidden;
	}
	.nav-left,
	.nav-right {
		position: absolute;
		z-index: 10;
		display: flex;
		flex-direction: column;
		align-items: center;
		gap: 6px;
	}
	.nav-left { left: 14px; }
	.nav-right { right: 14px; }
	.nav-circle {
		width: 38px;
		height: 38px;
		border-radius: 50%;
		background: var(--floating-control-bg);
		border: 1px solid var(--border2);
		font-size: 20px;
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--floating-control-fg);
		cursor: pointer;
		font-family: inherit;
		transition: background 0.1s;
	}
	.nav-circle:hover:not(:disabled) { background: var(--floating-control-hover); }
	.nav-circle:disabled {
		background: var(--floating-control-disabled-bg);
		color: var(--floating-control-muted);
		opacity: 1;
		cursor: not-allowed;
	}
	.nav-counter { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; white-space: nowrap; }
	.canvas-content {
		position: relative;
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}
	.canvas-content.side-nav-safe {
		box-sizing: border-box;
		padding-left: 68px;
		padding-right: 68px;
	}
	.canvas-content.can-pan { cursor: grab; touch-action: none; }
	.canvas-content.dragging { cursor: grabbing; }
	.canvas-pan {
		display: flex;
		align-items: center;
		justify-content: center;
		will-change: transform;
	}
	.canvas-box {
		width: 400px;
		height: 400px;
		background: var(--panel);
		box-shadow: 0 8px 32px rgba(0,0,0,0.18);
		overflow: hidden;
		flex-shrink: 0;
	}
	.canvas-box :global(svg) { width: 100%; height: 100%; display: block; }
	.canvas-placeholder-art {
		width: 100%;
		height: 100%;
		min-height: 200px;
		display: flex;
		align-items: center;
		justify-content: center;
		color: var(--fg3);
		font-size: 13px;
		background: var(--canvas-paper);
	}
	.canvas-placeholder-art svg {
		width: 100%;
		height: 100%;
		display: block;
	}
	.zoom-controls {
		position: absolute;
		bottom: 14px;
		left: 50%;
		transform: translateX(-50%);
		z-index: 10;
		display: flex;
		align-items: center;
		gap: 0;
		background: var(--floating-control-bg);
		border: 1px solid var(--border2);
		border-radius: 20px;
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		overflow: hidden;
	}
	.zoom-controls button {
		width: 32px;
		height: 28px;
		border: none;
		background: none;
		font-size: 16px;
		color: var(--floating-control-fg);
		cursor: pointer;
		display: flex;
		align-items: center;
		justify-content: center;
		font-family: inherit;
	}
	.zoom-controls button:hover { background: var(--floating-control-hover); }
	.zoom-pct {
		font-size: 11px;
		color: var(--floating-control-fg);
		font-weight: 500;
		font-variant-numeric: tabular-nums;
		min-width: 38px;
		text-align: center;
		user-select: none;
	}
	.zoom-reset { border-left: 1px solid var(--border) !important; font-size: 11px !important; color: var(--floating-control-muted) !important; }
	.status-bar {
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 8px 16px;
		border-top: 1px solid var(--border);
		background: var(--bg);
		flex-shrink: 0;
	}
	.status-summary {
		min-width: 0;
		margin-right: auto;
		display: flex;
		align-items: center;
		gap: 10px;
		color: var(--fg2);
		font-size: 11px;
		line-height: 1;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.status-group {
		min-width: 0;
		display: inline-flex;
		align-items: center;
		gap: 6px;
		line-height: 1;
	}
	.status-label {
		color: var(--fg3);
		font-size: 11px;
		font-weight: 400;
		letter-spacing: 0;
		text-transform: none;
	}
	.status-k {
		color: var(--fg3);
		font-size: 11px;
	}
	.status-v {
		min-width: 0;
		max-width: 260px;
		overflow: hidden;
		text-overflow: ellipsis;
		color: #4d5f86;
		font-size: 11px;
		font-weight: 400;
	}
	.status-divider {
		width: 1px;
		height: 16px;
		background: var(--border2);
		flex-shrink: 0;
	}
	.status-export-label { font-size: 11px; color: var(--fg3); white-space: nowrap; }
	.star-btn {
		width: 24px;
		height: 24px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		background: var(--panel);
		color: var(--fg3);
		font-size: 15px;
		line-height: 1;
		cursor: pointer;
		font-family: inherit;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.star-btn.starred { color: #d59b21; border-color: rgba(213,155,33,0.55); background: #fff7dc; }
	.star-btn:disabled { opacity: 0.35; cursor: not-allowed; }
	.status-star { flex-shrink: 0; }
	.png-wrap { position: relative; }
	.png-menu {
		position: absolute;
		bottom: calc(100% + 6px);
		right: 0;
		z-index: 100;
		background: var(--panel);
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		overflow: hidden;
		box-shadow: 0 4px 18px rgba(0,0,0,0.12);
		min-width: 220px;
	}
	.png-menu button {
		display: flex;
		align-items: center;
		gap: 8px;
		width: 100%;
		text-align: left;
		padding: 8px 14px;
		background: none;
		border: none;
		border-bottom: 1px solid var(--border);
		color: var(--fg);
		cursor: pointer;
		font-family: inherit;
		font-size: 13px;
		white-space: nowrap;
	}
	.png-menu button:last-child { border-bottom: none; }
	.png-menu button:hover { background: var(--bg); }
	.png-size { font-weight: 500; }
	.png-sub { color: var(--fg3); font-size: 11px; white-space: nowrap; }
	.ghost-btn {
		padding: 4px 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		font-family: inherit;
		cursor: pointer;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.ghost-btn:disabled { opacity: 0.4; cursor: not-allowed; }
</style>
