<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import OutputTabsContent from './OutputTabsContent.svelte';

	type OutputTab = 'canvas' | 'prompts' | 'score';
	type SvgProfile = 'display' | 'editable' | 'compat';
	type PaintResult = { svg: string; score: { instructions: unknown[]; canvas?: string | null }; render_hash?: string | null; render_hash_short?: string | null; render_seed?: number | null; vary_seed?: number | null };
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
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		zoom: number;
		actualZoom: number;
		canPan: boolean;
		panX: number;
		panY: number;
		canvasDragging: boolean;
		promptsData: PromptsData | null;
		stage1PromptText: string;
		instructionText: string;
		ddl: string | null;
		promptStage1Expanded: boolean;
		promptStage2Expanded: boolean;
		copiedPrompt: 'stage1' | 'stage2' | 'score' | null;
		scoreJsonText: string;
		scoreJsonLines: string[];
		scoreJsonHighlighted: string;
		scoreJsonSeparatorLine: number | null;
		statusStage1Model: string;
		statusStage2Model: string;
		statusCatalogName: string;
		statusCanvasName: string;
		statusHistoryItem: HistoryItem | null;
		statusHashLabel: string;
		statusHashCopyTitle: string;
		statusHashCopied: boolean;
		pngMenuOpen: boolean;
		pngWrapEl: HTMLDivElement | null;
		pngTemplates: ExportTemplate[];
		onGotoNext: () => void | Promise<void>;
		onGotoPrev: () => void | Promise<void>;
		onGotoLatest: () => void | Promise<void>;
		onPointerDown: (event: PointerEvent) => void;
		onPointerMove: (event: PointerEvent) => void;
		onPointerUp: (event: PointerEvent) => void;
		onSetZoom: (zoom: number) => void;
		onResetZoom: () => void;
		onFitZoomChange: (zoom: number) => void;
		onCopyPromptText: (kind: 'stage1' | 'stage2' | 'score', text: string | null | undefined) => void | Promise<void>;
		onCopyStatusHash: () => void | Promise<void>;
		onToggleStar: (item: HistoryItem | null | undefined, event?: Event) => void | Promise<void>;
		onDownloadSVG: (profile: SvgProfile) => void | Promise<void>;
		onDownloadPNG: (size: number) => void | Promise<void>;
		onVaryPerformance: () => void | Promise<void>;
		onVaryComposition: () => void | Promise<void>;
		onVaryInterpretation: () => void | Promise<void>;
		variationBusy: boolean;
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
		canvasAspectWidth = 1,
		canvasAspectHeight = 1,
		zoom,
		actualZoom,
		canPan,
		panX,
		panY,
		canvasDragging,
		promptsData,
		stage1PromptText,
		instructionText,
		ddl,
		promptStage1Expanded = $bindable(false),
		promptStage2Expanded = $bindable(false),
		copiedPrompt,
		scoreJsonText,
		scoreJsonLines,
		scoreJsonHighlighted,
		scoreJsonSeparatorLine,
		statusStage1Model,
		statusStage2Model,
		statusCatalogName,
		statusCanvasName,
		statusHistoryItem,
		statusHashLabel,
		statusHashCopyTitle,
		statusHashCopied,
		pngMenuOpen = $bindable(false),
		pngWrapEl = $bindable(null),
		pngTemplates,
		onGotoNext,
		onGotoPrev,
		onGotoLatest,
		onPointerDown,
		onPointerMove,
		onPointerUp,
		onSetZoom,
		onResetZoom,
		onFitZoomChange,
		onCopyPromptText,
		onCopyStatusHash,
		onToggleStar,
		onDownloadSVG,
		onDownloadPNG,
		onVaryPerformance,
		onVaryComposition,
		onVaryInterpretation,
		variationBusy = false
	}: Props = $props();

	let canvasContentEl: HTMLDivElement | null = null;
	let svgMenuOpen = $state(false);
	let svgHelpOpen = $state(false);
	let instructionCaptionVisible = $state(true);
	let presentationMode = $state(false);
	const canvasMaxRatio = $derived(Math.max(canvasAspectWidth, canvasAspectHeight, 1));
	const canvasBaseWidth = $derived(400 * canvasAspectWidth / canvasMaxRatio);
	const canvasBaseHeight = $derived(400 * canvasAspectHeight / canvasMaxRatio);
	const placeholderUnit = $derived(Math.max(0.001, Math.min(canvasAspectWidth, canvasAspectHeight)));
	const placeholderWidth = $derived(Math.round(1000 * canvasAspectWidth / placeholderUnit));
	const placeholderHeight = $derived(Math.round(1000 * canvasAspectHeight / placeholderUnit));
	const displayInstructionText = $derived((instructionText || '').trim());
	const canShowInstructionCaption = $derived(!!displayInstructionText);

	function updateFitZoom() {
		if (!canvasContentEl) return;
		const rect = canvasContentEl.getBoundingClientRect();
		const availableWidth = Math.max(120, rect.width - 120);
		const availableHeight = Math.max(120, rect.height - 96);
		const nextZoom = Math.max(0.25, Math.min(10, Math.min(availableWidth / canvasBaseWidth, availableHeight / canvasBaseHeight)));
		onFitZoomChange(+nextZoom.toFixed(2));
	}

	onMount(() => {
		updateFitZoom();
		const observer = new ResizeObserver(updateFitZoom);
		if (canvasContentEl) observer.observe(canvasContentEl);
		return () => observer.disconnect();
	});

	$effect(() => {
		canvasAspectWidth;
		canvasAspectHeight;
		updateFitZoom();
	});

	function isDefaultPngTemplate(template: ExportTemplate): boolean {
		return template.id === `png-${template.y_px}` && [1080, 2160, 4320].includes(template.y_px);
	}

	function pngTemplateDescription(template: ExportTemplate): string {
		if (isDefaultPngTemplate(template)) return t().pngYAxisDescription(template.y_px);
		return template.description || t().pngYAxisDescription(template.y_px);
	}

	function closePresentationMode() {
		presentationMode = false;
	}

	const seedSummary = $derived(
		result
			? t().canvasSeedSummary
				.replace('{render}', result.render_seed == null ? '-' : String(result.render_seed))
				.replace('{vary}', result.vary_seed == null ? '-' : String(result.vary_seed))
			: ''
	);
</script>

<svelte:window onkeydown={(event) => {
	if (event.key === 'Escape' && presentationMode) closePresentationMode();
}} />

<div class="right-panel">
	<div class="right-tabs">
		<button class="rtab" class:active={outputTab === 'canvas'} onclick={() => (outputTab = 'canvas')}>{t().tabCanvas}</button>
		<button class="rtab" class:active={outputTab === 'prompts'} onclick={() => (outputTab = 'prompts')} disabled={!result && !allowEmptyOutputTabs}>{t().tabPrompts}</button>
		<button class="rtab" class:active={outputTab === 'score'} onclick={() => (outputTab = 'score')} disabled={!result && !allowEmptyOutputTabs}>{t().tabScore}</button>
		<div class="rtab-spacer"></div>
		{#if currentRenderedAt}
			<div class="render-meta-strip">
				<span class="render-meta-item render-meta-catalog">
					<span class="render-meta-label">{t().historyCatalogHeader}</span>
					<strong>{statusCatalogName}</strong>
				</span>
				<span class="render-meta-item render-meta-canvas">
					<span class="render-meta-label">{t().historyCanvasHeader}</span>
					<strong>{statusCanvasName}</strong>
				</span>
				<span class="render-meta-item render-meta-created">
					<span class="render-meta-label">{t().historyCreatedAtHeader}</span>
					<strong>{currentRenderedAt}</strong>
				</span>
			</div>
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
						style="width: {canvasBaseWidth}px; height: {canvasBaseHeight}px; transform: scale({actualZoom}); transform-origin: center center; transition: transform 0.15s;"
					>
						{#if result}
							{@html result.svg}
						{:else}
							<div class="canvas-placeholder-art" aria-label={t().canvasPlaceholder}>
								<svg viewBox="0 0 {placeholderWidth} {placeholderHeight}" role="img">
									<rect x="0" y="0" width={placeholderWidth} height={placeholderHeight} rx="6" fill="#fffdf8" />
									<g opacity="0.72">
										<path d="M {placeholderWidth * 0.16} {placeholderHeight * 0.67} C {placeholderWidth * 0.26} {placeholderHeight * 0.52} {placeholderWidth * 0.35} {placeholderHeight * 0.78} {placeholderWidth * 0.46} {placeholderHeight * 0.61} S {placeholderWidth * 0.65} {placeholderHeight * 0.40} {placeholderWidth * 0.83} {placeholderHeight * 0.58}" fill="none" stroke="#cfc6b6" stroke-width="7" stroke-linecap="round" />
										<path d="M {placeholderWidth * 0.17} {placeholderHeight * 0.38} C {placeholderWidth * 0.26} {placeholderHeight * 0.32} {placeholderWidth * 0.33} {placeholderHeight * 0.42} {placeholderWidth * 0.41} {placeholderHeight * 0.37} C {placeholderWidth * 0.49} {placeholderHeight * 0.32} {placeholderWidth * 0.56} {placeholderHeight * 0.22} {placeholderWidth * 0.66} {placeholderHeight * 0.28} C {placeholderWidth * 0.73} {placeholderHeight * 0.32} {placeholderWidth * 0.78} {placeholderHeight * 0.39} {placeholderWidth * 0.85} {placeholderHeight * 0.36}" fill="none" stroke="#ded6c9" stroke-width="4" stroke-linecap="round" stroke-dasharray="18 18" />
										<circle cx={placeholderWidth * 0.33} cy={placeholderHeight * 0.53} r={Math.min(placeholderWidth, placeholderHeight) * 0.055} fill="none" stroke="#d8cfc0" stroke-width="6" />
										<rect x={placeholderWidth * 0.63} y={placeholderHeight * 0.48} width={placeholderWidth * 0.09} height={placeholderHeight * 0.11} rx="2" fill="none" stroke="#d8cfc0" stroke-width="6" transform="rotate(-12 {placeholderWidth * 0.675} {placeholderHeight * 0.535})" />
										<path d="M {placeholderWidth * 0.49} {placeholderHeight * 0.40} L {placeholderWidth * 0.54} {placeholderHeight * 0.57} L {placeholderWidth * 0.44} {placeholderHeight * 0.57} Z" fill="none" stroke="#d8cfc0" stroke-width="6" stroke-linejoin="round" />
									</g>
								</svg>
							</div>
						{/if}
					</div>
				</div>
				<div class="canvas-corner-controls canvas-corner-left" onpointerdown={(event) => event.stopPropagation()}>
					<button
						type="button"
						class="canvas-icon-btn"
						class:active={instructionCaptionVisible}
						disabled={!canShowInstructionCaption}
						title={t().canvasCaptionToggle}
						aria-label={t().canvasCaptionToggle}
						onclick={(event) => {
							event.stopPropagation();
							instructionCaptionVisible = !instructionCaptionVisible;
						}}
					>
						<svg viewBox="0 0 24 24" aria-hidden="true">
							<rect x="3.5" y="5.5" width="17" height="13" rx="2.5" />
							<path d="M7.5 10.5h4.5M14.5 10.5h2M7.5 14h3M13 14h3.5" />
						</svg>
					</button>
				</div>
				<div class="canvas-corner-controls canvas-corner-right" onpointerdown={(event) => event.stopPropagation()}>
					<button
						type="button"
						class="canvas-icon-btn"
						disabled={!result}
						title={t().canvasPresentationOpen}
						aria-label={t().canvasPresentationOpen}
						onclick={(event) => {
							event.stopPropagation();
							presentationMode = true;
						}}
					>
						<svg viewBox="0 0 24 24" aria-hidden="true">
							<path d="M8.5 4.5h-4v4M15.5 4.5h4v4M8.5 19.5h-4v-4M15.5 19.5h4v-4" />
							<path d="M8 8 4.5 4.5M16 8l3.5-3.5M8 16l-3.5 3.5M16 16l3.5 3.5" />
						</svg>
					</button>
				</div>
				{#if instructionCaptionVisible && canShowInstructionCaption}
					<div class="instruction-caption" aria-live="polite">{displayInstructionText}</div>
				{/if}
			{:else if outputTab === 'prompts'}
				<OutputTabsContent
					outputTab="prompts"
					{promptsData}
					{stage1PromptText}
					{ddl}
					bind:promptStage1Expanded
					bind:promptStage2Expanded
					{copiedPrompt}
					{scoreJsonText}
					{scoreJsonLines}
					{scoreJsonHighlighted}
					{scoreJsonSeparatorLine}
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
					{scoreJsonText}
					{scoreJsonLines}
					{scoreJsonHighlighted}
					{scoreJsonSeparatorLine}
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

		<!-- svelte-ignore a11y_no_static_element_interactions -->
		<div class="variation-controls" onpointerdown={(event) => event.stopPropagation()}>
			<button class="ghost-btn variation-btn" onclick={onVaryPerformance} disabled={!result || variationBusy}>{t().canvasVaryPerformance}</button>
			<button class="ghost-btn variation-btn" onclick={onVaryComposition} disabled={!result || variationBusy}>{t().canvasVaryComposition}</button>
			<button class="ghost-btn variation-btn" onclick={onVaryInterpretation} disabled={!result || variationBusy}>{t().canvasVaryInterpretation}</button>
			{#if result}<span class="seed-summary">{seedSummary}</span>{/if}
		</div>

		<div class="nav-right">
			<button class="nav-latest" onclick={onGotoLatest} disabled={nextDisabled}>{t().historyLatest}</button>
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
			<span class="status-divider"></span>
			<span class="status-group">
				<span class="status-label">Canvas</span>
				<span class="status-v">{statusCanvasName}</span>
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
		<button
			class="hash-copy-btn"
			class:copied={statusHashCopied}
			disabled={!result || !statusHashLabel}
			onclick={onCopyStatusHash}
			title={statusHashCopyTitle}
			aria-label={statusHashCopyTitle}
		>{statusHashCopied ? t().promptCopied : statusHashLabel || '----'}</button>
		<div class="png-wrap">
			<button class="ghost-btn export-btn" onclick={(e) => { e.stopPropagation(); svgMenuOpen = !svgMenuOpen; }} disabled={!result}>
				<svg class="download-icon" viewBox="0 0 24 24" aria-hidden="true">
					<path d="M12 3v11m0 0 4-4m-4 4-4-4M5 18h14" />
				</svg>
				<span>SVG</span>
				<span class="menu-caret">▾</span>
			</button>
			{#if svgMenuOpen}
				<div class="png-menu">
					<div class="svg-menu-head">
						<span>{t().svgExportHelpTitle}</span>
						<button
							type="button"
							class="svg-help-btn"
							aria-label={t().svgExportHelpAria}
							onclick={(e) => { e.stopPropagation(); svgHelpOpen = !svgHelpOpen; }}
						>?</button>
					</div>
					{#if svgHelpOpen}
						<div class="svg-help-popover">
							<table>
								<thead>
									<tr><th>{t().svgExportTableFormat}</th><th>{t().svgExportTableUse}</th><th>{t().svgExportTableFeature}</th></tr>
								</thead>
								<tbody>
									<tr><td>{t().svgExportDisplayName}</td><td>{t().svgExportDisplayUse}</td><td>{t().svgExportDisplayFeature}</td></tr>
									<tr><td>{t().svgExportEditableName}</td><td>{t().svgExportEditableUse}</td><td>{t().svgExportEditableFeature}</td></tr>
									<tr><td>{t().svgExportCompatName}</td><td>{t().svgExportCompatUse}</td><td>{t().svgExportCompatFeature}</td></tr>
								</tbody>
							</table>
						</div>
					{/if}
					<button onclick={() => { onDownloadSVG('display'); svgMenuOpen = false; }}>
						<span class="png-size">{t().svgExportDisplayName}</span>
						<span class="png-sub">{t().svgExportDisplaySub}</span>
					</button>
					<button onclick={() => { onDownloadSVG('editable'); svgMenuOpen = false; }}>
						<span class="png-size">{t().svgExportEditableName}</span>
						<span class="png-sub">{t().svgExportEditableSub}</span>
					</button>
					<button onclick={() => { onDownloadSVG('compat'); svgMenuOpen = false; }}>
						<span class="png-size">{t().svgExportCompatName}</span>
						<span class="png-sub">{t().svgExportCompatSub}</span>
					</button>
				</div>
			{/if}
		</div>
		<div class="png-wrap" bind:this={pngWrapEl}>
			<button class="ghost-btn export-btn" onclick={(e) => { e.stopPropagation(); pngMenuOpen = !pngMenuOpen; }} disabled={!result}>
				<svg class="download-icon" viewBox="0 0 24 24" aria-hidden="true">
					<path d="M12 3v11m0 0 4-4m-4 4-4-4M5 18h14" />
				</svg>
				<span>PNG</span>
				<span class="menu-caret">▾</span>
			</button>
			{#if pngMenuOpen}
				<div class="png-menu">
					{#each pngTemplates as template (template.id)}
						<button onclick={() => { onDownloadPNG(template.y_px); pngMenuOpen = false; }}>
							<span class="png-size">{template.name}</span>
							<span class="png-sub">{pngTemplateDescription(template)}</span>
						</button>
					{/each}
				</div>
			{/if}
		</div>
	</div>
</div>

{#if presentationMode && result}
	<div class="presentation-overlay" role="dialog" aria-modal="true" aria-label={t().canvasPresentationTitle}>
		<div class="presentation-stage">
			<div class="presentation-art">
				{@html result.svg}
			</div>
			{#if instructionCaptionVisible && canShowInstructionCaption}
				<div class="presentation-caption">{displayInstructionText}</div>
			{/if}
		</div>
		<div class="presentation-controls" aria-label={t().canvasPresentationControls}>
			<button type="button" class="presentation-icon-btn" onclick={onGotoNext} disabled={nextDisabled} title={t().historyOlderPage(1)} aria-label={t().historyOlderPage(1)}>
				‹
			</button>
			<button type="button" class="presentation-text-btn" onclick={onGotoLatest} disabled={nextDisabled}>{t().historyLatest}</button>
			<button type="button" class="presentation-icon-btn" onclick={onGotoPrev} disabled={prevDisabled} title={t().historyNewerPage(1)} aria-label={t().historyNewerPage(1)}>
				›
			</button>
			<span class="presentation-counter">{historyTotal > 0 ? `${navPos} / ${historyTotal}` : ''}</span>
			<button
				type="button"
				class="presentation-icon-btn presentation-star-btn"
				class:starred={!!statusHistoryItem?.starred}
				disabled={!statusHistoryItem?.id}
				onclick={(event) => onToggleStar(statusHistoryItem, event)}
				title={statusHistoryItem?.starred ? t().starOn : t().starOff}
				aria-label={statusHistoryItem?.starred ? t().starOn : t().starOff}
			>
				★
			</button>
			<button
				type="button"
				class="presentation-icon-btn"
				class:active={instructionCaptionVisible}
				disabled={!canShowInstructionCaption}
				onclick={() => (instructionCaptionVisible = !instructionCaptionVisible)}
				title={t().canvasCaptionToggle}
				aria-label={t().canvasCaptionToggle}
			>
				<svg viewBox="0 0 24 24" aria-hidden="true">
					<rect x="3.5" y="5.5" width="17" height="13" rx="2.5" />
					<path d="M7.5 10.5h4.5M14.5 10.5h2M7.5 14h3M13 14h3.5" />
				</svg>
			</button>
			<button type="button" class="presentation-icon-btn" onclick={closePresentationMode} title={t().canvasPresentationClose} aria-label={t().canvasPresentationClose}>
				<svg viewBox="0 0 24 24" aria-hidden="true">
					<path d="M6 6l12 12M18 6 6 18" />
				</svg>
			</button>
		</div>
	</div>
{/if}

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
	.rtab-spacer { flex: 1; min-width: 12px; }
	.render-meta-strip {
		display: flex;
		align-items: center;
		justify-content: flex-end;
		gap: 10px;
		min-width: 0;
		max-width: min(68vw, 760px);
		overflow: hidden;
		font-size: 11px;
		color: var(--fg3);
	}
	.render-meta-item {
		display: inline-flex;
		align-items: baseline;
		gap: 4px;
		min-width: 0;
		white-space: nowrap;
	}
	.render-meta-label { color: var(--fg3); }
	.render-meta-item strong {
		min-width: 0;
		max-width: 160px;
		overflow: hidden;
		text-overflow: ellipsis;
		color: var(--fg2);
		font-weight: 400;
	}
	.render-meta-created strong {
		max-width: none;
		font-variant-numeric: tabular-nums;
	}
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
	.variation-controls {
		position: absolute;
		left: 50%;
		bottom: 18px;
		transform: translateX(-50%);
		display: flex;
		align-items: center;
		gap: 8px;
		z-index: 12;
		background: color-mix(in srgb, var(--bg) 88%, transparent);
		border: 1px solid var(--border);
		padding: 6px 8px;
		box-shadow: var(--shadow-sm);
	}
	.variation-btn { min-width: 88px; }
	.seed-summary {
		font-size: 11px;
		color: var(--fg3);
		white-space: nowrap;
	}
	@media (max-width: 720px) {
		.variation-controls {
			left: 12px;
			right: 12px;
			transform: none;
			justify-content: center;
			flex-wrap: wrap;
		}
	}

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
	.nav-latest {
		min-width: 42px;
		height: 24px;
		border-radius: 999px;
		background: var(--floating-control-bg);
		border: 1px solid var(--border2);
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		color: var(--floating-control-fg);
		cursor: pointer;
		font-size: 11px;
		font-family: inherit;
		line-height: 1;
		padding: 0 8px;
	}
	.nav-latest:hover:not(:disabled) { background: var(--floating-control-hover); }
	.nav-circle:disabled {
		background: var(--floating-control-disabled-bg);
		color: var(--floating-control-muted);
		opacity: 1;
		cursor: not-allowed;
	}
	.nav-latest:disabled {
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
	.canvas-corner-controls {
		position: absolute;
		bottom: 14px;
		z-index: 11;
		display: flex;
		align-items: center;
		gap: 6px;
	}
	.canvas-corner-left { left: 18px; }
	.canvas-corner-right { right: 18px; }
	.canvas-icon-btn {
		width: 34px;
		height: 34px;
		border: 1px solid var(--border2);
		border-radius: 999px;
		background: var(--floating-control-bg);
		color: var(--floating-control-fg);
		box-shadow: 0 1px 6px rgba(0,0,0,0.1);
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		padding: 0;
	}
	.canvas-icon-btn:hover:not(:disabled),
	.canvas-icon-btn.active {
		background: var(--floating-control-hover);
		border-color: rgba(77,95,134,0.45);
	}
	.canvas-icon-btn:disabled {
		background: var(--floating-control-disabled-bg);
		color: var(--floating-control-muted);
		cursor: not-allowed;
	}
	.canvas-icon-btn svg {
		width: 18px;
		height: 18px;
		fill: none;
		stroke: currentColor;
		stroke-width: 1.9;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.instruction-caption {
		position: absolute;
		left: 10%;
		right: 10%;
		bottom: 58px;
		z-index: 12;
		box-sizing: border-box;
		padding: 9px 14px;
		border-radius: 8px;
		background: rgba(17,17,17,0.78);
		color: #fffdf8;
		font-size: 14px;
		line-height: 1.55;
		text-align: center;
		box-shadow: 0 4px 18px rgba(0,0,0,0.22);
		max-height: 5.1em;
		overflow: hidden;
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
	.export-btn {
		display: inline-flex;
		align-items: center;
		justify-content: center;
		gap: 5px;
		line-height: 1;
	}
	.download-icon {
		width: 14px;
		height: 14px;
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
		stroke-linejoin: round;
		flex: 0 0 auto;
		display: block;
		transform: translateY(0.5px);
	}
	.menu-caret {
		color: var(--fg3);
		font-size: 10px;
		line-height: 1;
	}
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
	.hash-copy-btn {
		height: 24px;
		min-width: 48px;
		padding: 0 8px;
		border: 1px solid var(--border2);
		border-radius: 999px;
		background: var(--panel);
		color: var(--fg2);
		font-size: 11px;
		line-height: 1;
		font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
		font-weight: 600;
		letter-spacing: 0;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex-shrink: 0;
	}
	.hash-copy-btn:hover:not(:disabled) {
		border-color: rgba(77,95,134,0.45);
		background: var(--bg2);
	}
	.hash-copy-btn.copied {
		border-color: rgba(70,130,90,0.45);
		color: #2f6b3a;
		background: rgba(47,107,58,0.10);
		font-family: inherit;
		font-weight: 600;
	}
	.hash-copy-btn:disabled { opacity: 0.35; cursor: not-allowed; }
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
	.png-menu > button {
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
	.png-menu > button:last-child { border-bottom: none; }
	.png-menu > button:hover { background: var(--bg); }
	.png-size { font-weight: 500; }
	.png-sub { color: var(--fg3); font-size: 11px; white-space: nowrap; }
	.svg-menu-head {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		padding: 8px 12px;
		border-bottom: 1px solid var(--border);
		color: var(--fg2);
		font-size: 12px;
		font-weight: 600;
	}
	.svg-help-btn {
		width: 18px;
		height: 18px;
		border: 1px solid var(--border2);
		border-radius: 50%;
		background: var(--bg);
		color: var(--fg2);
		font: inherit;
		font-size: 11px;
		line-height: 1;
		cursor: pointer;
		display: inline-flex;
		align-items: center;
		justify-content: center;
		flex: 0 0 auto;
		padding: 0;
	}
	.svg-help-popover {
		width: min(480px, calc(100vw - 48px));
		padding: 12px;
		border-bottom: 1px solid var(--border);
		background: var(--bg2);
		color: var(--fg);
	}
	.svg-help-popover table {
		width: 100%;
		border-collapse: collapse;
		font-size: 11px;
		line-height: 1.45;
	}
	.svg-help-popover th,
	.svg-help-popover td {
		padding: 6px 8px;
		border: 1px solid var(--border);
		text-align: left;
		vertical-align: top;
	}
	.svg-help-popover th {
		background: var(--bg);
		color: var(--fg2);
		font-weight: 700;
		white-space: nowrap;
	}
	.svg-help-popover td:first-child {
		white-space: nowrap;
		font-weight: 600;
	}
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
	.presentation-overlay {
		position: fixed;
		inset: 0;
		z-index: 1000;
		background: #101010;
		color: #fffdf8;
		display: grid;
		grid-template-rows: minmax(0, 1fr) auto;
		padding: clamp(16px, 3vw, 36px);
		box-sizing: border-box;
	}
	.presentation-stage {
		position: relative;
		min-width: 0;
		min-height: 0;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
	}
	.presentation-art {
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.presentation-art :global(svg) {
		max-width: 100%;
		max-height: 100%;
		width: auto;
		height: auto;
		display: block;
		box-shadow: 0 10px 42px rgba(0,0,0,0.42);
	}
	.presentation-caption {
		position: absolute;
		left: 10vw;
		right: 10vw;
		bottom: clamp(14px, 3vh, 32px);
		box-sizing: border-box;
		padding: 12px 18px;
		border-radius: 8px;
		background: rgba(0,0,0,0.72);
		color: #fffdf8;
		font-size: clamp(15px, 1.6vw, 24px);
		line-height: 1.55;
		text-align: center;
		box-shadow: 0 8px 30px rgba(0,0,0,0.34);
		max-height: 5.2em;
		overflow: hidden;
	}
	.presentation-controls {
		min-height: 46px;
		margin: 14px auto 0;
		padding: 6px;
		border: 1px solid rgba(255,255,255,0.18);
		border-radius: 999px;
		background: rgba(28,28,28,0.88);
		box-shadow: 0 8px 26px rgba(0,0,0,0.28);
		display: flex;
		align-items: center;
		justify-content: center;
		gap: 6px;
	}
	.presentation-icon-btn,
	.presentation-text-btn {
		height: 34px;
		border: 1px solid rgba(255,255,255,0.18);
		background: rgba(255,255,255,0.06);
		color: #fffdf8;
		cursor: pointer;
		font-family: inherit;
		display: inline-flex;
		align-items: center;
		justify-content: center;
	}
	.presentation-icon-btn {
		width: 34px;
		border-radius: 50%;
		font-size: 19px;
		padding: 0;
	}
	.presentation-text-btn {
		border-radius: 999px;
		font-size: 12px;
		padding: 0 12px;
		white-space: nowrap;
	}
	.presentation-icon-btn:hover:not(:disabled),
	.presentation-text-btn:hover:not(:disabled),
	.presentation-icon-btn.active {
		background: rgba(255,255,255,0.16);
	}
	.presentation-star-btn {
		color: rgba(255,253,248,0.62);
		font-size: 17px;
	}
	.presentation-star-btn.starred {
		color: #ffd45c;
		border-color: rgba(255,212,92,0.62);
		background: rgba(255,212,92,0.14);
	}
	.presentation-icon-btn:disabled,
	.presentation-text-btn:disabled {
		opacity: 0.35;
		cursor: not-allowed;
	}
	.presentation-icon-btn svg {
		width: 18px;
		height: 18px;
		fill: none;
		stroke: currentColor;
		stroke-width: 2;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.presentation-counter {
		min-width: 44px;
		padding: 0 6px;
		color: rgba(255,253,248,0.72);
		font-size: 12px;
		font-variant-numeric: tabular-nums;
		text-align: center;
		white-space: nowrap;
	}
	@media (max-width: 720px) {
		.instruction-caption {
			left: 10%;
			right: 10%;
			bottom: 58px;
			font-size: 13px;
		}
		.presentation-overlay {
			padding: 12px;
		}
		.presentation-controls {
			width: 100%;
			box-sizing: border-box;
			border-radius: 12px;
			flex-wrap: wrap;
		}
	}
</style>
