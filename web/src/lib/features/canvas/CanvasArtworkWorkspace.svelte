<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { placeholderMotifTransform } from '$lib/canvas-placeholder';
	import type { ExportTemplate } from '$lib/exportTemplates';
	import { shareTargetOf } from '$lib/shareTarget';
	import type { CanvasViewport } from '$lib/features/canvas/viewport-state.svelte';
	import type { PaintResult } from '$lib/features/run/current-work';
	import type { SvgProfile } from '$lib/features/export/download';
	import type { CanvasStatusHistoryItem } from './view-types';
	import Tooltip from '$lib/components/Tooltip.svelte';
	import CaptionText from '$lib/components/CaptionText.svelte';

	type Props = {
		result: PaintResult | null;
		artworkUrl: string | null;
		canvasContentEl: HTMLDivElement | null;
		canvasAspectWidth: number;
		canvasAspectHeight: number;
		canvasBaseWidth: number;
		canvasBaseHeight: number;
		viewport: CanvasViewport;
		unsavedRefinementPreview: boolean;
		interpretFallbackReason: string | null;
		composeFallbackDrawnReason: string | null;
		lineageIntermediateNotice: string | null;
		instructionCaptionVisible: boolean;
		canShowInstructionCaption: boolean;
		displayInstructionText: string;
		statusHistoryItem: CanvasStatusHistoryItem | null;
		statusHashLabel: string;
		statusHashCopied: boolean;
		replayDisabled: boolean;
		allowEmptyOutputTabs: boolean;
		generationInfoOpen: boolean;
		generationInfoToggleEl: HTMLButtonElement | null;
		exportMenuOpen: boolean;
		exportWrapEl: HTMLDivElement | null;
		exportCardOnly: boolean;
		cardExportBusy: boolean;
		svgHelpOpen: boolean;
		currentHistoryId: string | null;
		pngTemplates: ExportTemplate[];
		isJapanese: boolean;
		onToggleInstructionCaption: () => void;
		onToggleStar: (item: CanvasStatusHistoryItem | null | undefined, event?: Event) => void | Promise<void>;
		onToggleForRevision: (item: CanvasStatusHistoryItem | null | undefined, event?: Event) => void | Promise<void>;
		onToggleForShare?: ((item: CanvasStatusHistoryItem | null | undefined, event?: Event) => void | Promise<void>) | null;
		onCopyStatusHash: () => void | Promise<void>;
		onReplayCurrent: () => void | Promise<void>;
		onToggleGenerationInfo: () => void;
		onToggleSaijiki: () => void;
		onDownloadSVG: (profile: SvgProfile) => void | Promise<void>;
		onDownloadPNG: (size: number) => void | Promise<void>;
		onDownloadCard: () => void | Promise<void>;
		onOpenPresentation: () => void;
	};

	let {
		result,
		artworkUrl,
		canvasContentEl = $bindable(null),
		canvasAspectWidth,
		canvasAspectHeight,
		canvasBaseWidth,
		canvasBaseHeight,
		viewport,
		unsavedRefinementPreview,
		interpretFallbackReason,
		composeFallbackDrawnReason,
		lineageIntermediateNotice,
		instructionCaptionVisible,
		canShowInstructionCaption,
		displayInstructionText,
		statusHistoryItem,
		statusHashLabel,
		statusHashCopied,
		replayDisabled,
		allowEmptyOutputTabs,
		generationInfoOpen,
		generationInfoToggleEl = $bindable(null),
		exportMenuOpen = $bindable(false),
		exportWrapEl = $bindable(null),
		exportCardOnly,
		cardExportBusy,
		svgHelpOpen = $bindable(false),
		currentHistoryId,
		pngTemplates,
		isJapanese,
		onToggleInstructionCaption,
		onToggleStar,
		onToggleForRevision,
		onToggleForShare = null,
		onCopyStatusHash,
		onReplayCurrent,
		onToggleGenerationInfo,
		onToggleSaijiki,
		onDownloadSVG,
		onDownloadPNG,
		onDownloadCard,
		onOpenPresentation
	}: Props = $props();

	const placeholderUnit = $derived(Math.max(0.001, Math.min(canvasAspectWidth, canvasAspectHeight)));
	const placeholderWidth = $derived(Math.round(1000 * canvasAspectWidth / placeholderUnit));
	const placeholderHeight = $derived(Math.round(1000 * canvasAspectHeight / placeholderUnit));
	// The motif is authored in one square and placed with one uniform scale. This
	// keeps circles and angles intact on every canvas proportion.
	const placeholderTransform = $derived(placeholderMotifTransform(placeholderWidth, placeholderHeight));
	const shareTarget = $derived(shareTargetOf(statusHistoryItem));

	function isDefaultPngTemplate(template: ExportTemplate): boolean {
		return template.id === `png-${template.y_px}` && [1080, 2160, 4320].includes(template.y_px);
	}

	function pngTemplateDescription(template: ExportTemplate): string {
		if (isDefaultPngTemplate(template)) return t().pngYAxisDescription(template.y_px);
		return template.description || t().pngYAxisDescription(template.y_px);
	}
</script>

<!-- svelte-ignore a11y_no_static_element_interactions -->
<div
	bind:this={canvasContentEl}
	class="canvas-content"
	class:can-pan={viewport.canPan}
	class:dragging={viewport.dragging}
	onpointerdown={(event) => viewport.startDrag(event, true)}
	onpointermove={(event) => viewport.moveDrag(event)}
	onpointerup={(event) => viewport.endDrag(event)}
	onpointercancel={(event) => viewport.endDrag(event)}
>
				<div class="canvas-pan" style="transform: translate3d({viewport.panX}px, {viewport.panY}px, 0);">
					<div
						class="canvas-box"
						style="width: {canvasBaseWidth}px; height: {canvasBaseHeight}px; transform: scale({viewport.actualZoom}); transform-origin: center center; transition: transform 0.15s;"
					>
						{#if result}
							{#if artworkUrl}
								<img class="canvas-art" src={artworkUrl} alt="" />
							{/if}
						{:else}
							<div class="canvas-placeholder-art" aria-label={t().canvasPlaceholder}>
								<svg viewBox="0 0 {placeholderWidth} {placeholderHeight}" role="img">
									<rect x="0" y="0" width={placeholderWidth} height={placeholderHeight} rx="6" fill="#fffdf8" />
									<!-- Mountain, water, moon: three strokes, authored inside the
									     1000-square PLACEHOLDER_MOTIF frame and placed by one uniform
									     scale, so the moon stays round and the ridge keeps its angles
									     at every canvas proportion. No coordinate here is written as a
									     fraction of the frame -- that is what turned the old triangle
									     into a needle at Pillar (1:5). -->
									<g opacity="0.72" transform={placeholderTransform}>
										<path d="M 110 645 L 320 360 L 505 545 L 640 445 L 890 645" fill="none" stroke="#cfc6b6" stroke-width="7" stroke-linecap="round" stroke-linejoin="round" />
										<path d="M 110 748 C 215 700 300 800 400 748 C 500 696 585 796 685 748 C 780 700 838 782 890 754" fill="none" stroke="#ded6c9" stroke-width="4" stroke-linecap="round" />
										<circle cx="690" cy="260" r="80" fill="none" stroke="#d8cfc0" stroke-width="6" />
									</g>
								</svg>
							</div>
						{/if}
					</div>
				</div>
{#if unsavedRefinementPreview}
	<div class="unsaved-refinement-badge" role="status">{t().unsavedRefinementPreviewLabel}</div>
{/if}
{#if interpretFallbackReason || composeFallbackDrawnReason}
	<!-- Stacked, and one badge per layer: a work whose interpretation and whose
	     composition both fell has lost the words twice, and a single badge would
	     say it once. The wording names the layer for the same reason. -->
	<div class="fallback-badges" role="status">
		{#if interpretFallbackReason}
			<div class="interpret-fallback-badge" title={t().interpretFallbackHint(interpretFallbackReason)}>{t().interpretFallbackBadge}</div>
		{/if}
		{#if composeFallbackDrawnReason}
			<Tooltip placement="bottom-left" text={t().composeFallbackHint(composeFallbackDrawnReason)} wide>
				<span class="compose-fallback-badge">{t().composeFallbackBadge}</span>
			</Tooltip>
		{/if}
	</div>
{/if}
{#if lineageIntermediateNotice}
	<div class="lineage-intermediate-notice" role="status">{lineageIntermediateNotice}</div>
{/if}
				<!-- The marks a reader puts on the work in front of them: it is a
				     favourite, it wants another pass. They sit beside the caption
				     toggle rather than in a bar of their own, because all three are
				     about the drawing on screen and nothing else. -->
				<div class="canvas-corner-controls canvas-corner-left" onpointerdown={(event) => event.stopPropagation()}>
					<Tooltip placement="top-right" text={t().tooltipCanvasCaption}>
						<button
							type="button"
							class="canvas-icon-btn canvas-caption-btn"
							class:active={instructionCaptionVisible}
							disabled={!canShowInstructionCaption}
							aria-label={t().canvasCaptionToggle}
							onclick={(event) => {
								event.stopPropagation();
								onToggleInstructionCaption();
							}}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<rect x="3.5" y="5.5" width="17" height="13" rx="2.5" />
								<path d="M7.5 10.5h4.5M14.5 10.5h2M7.5 14h3M13 14h3.5" />
							</svg>
						</button>
					</Tooltip>
					<Tooltip placement="top-right" text={statusHistoryItem?.starred ? t().starOn : t().starOff}>
						<button
							type="button"
							class="canvas-icon-btn canvas-star-btn"
							class:marked={!!statusHistoryItem?.starred}
							disabled={!statusHistoryItem?.id}
							aria-pressed={!!statusHistoryItem?.starred}
							aria-label={statusHistoryItem?.starred ? t().starOn : t().starOff}
							onclick={(event) => {
								event.stopPropagation();
								onToggleStar(statusHistoryItem, event);
							}}
						>★</button>
					</Tooltip>
					<Tooltip placement="top-right" text={statusHistoryItem?.for_revision ? t().forRevisionOn : t().forRevisionOff}>
						<button
							type="button"
							class="canvas-icon-btn canvas-revision-btn"
							class:marked={!!statusHistoryItem?.for_revision}
							disabled={!statusHistoryItem?.id}
							aria-pressed={!!statusHistoryItem?.for_revision}
							aria-label={statusHistoryItem?.for_revision ? t().forRevisionOn : t().forRevisionOff}
							onclick={(event) => {
								event.stopPropagation();
								onToggleForRevision(statusHistoryItem, event);
							}}
						>✎</button>
					</Tooltip>
					{#if shareTarget.supported && onToggleForShare}
						<Tooltip placement="top-right" text={shareTarget.marked ? t().shareTargetOn : t().shareTargetOff}>
							<button
								type="button"
								class="canvas-icon-btn canvas-share-btn"
								class:marked={shareTarget.marked}
								disabled={!shareTarget.pressable}
								aria-pressed={shareTarget.marked}
								aria-label={shareTarget.marked ? t().shareTargetOn : t().shareTargetOff}
								onclick={(event) => {
									event.stopPropagation();
									onToggleForShare?.(statusHistoryItem, event);
								}}
							>
								<svg viewBox="0 0 24 24" aria-hidden="true">
									<circle cx="17.5" cy="6" r="2.6" />
									<circle cx="6.5" cy="12" r="2.6" />
									<circle cx="17.5" cy="18" r="2.6" />
									<path d="M9 10.7 15 7.3M9 13.3l6 3.4" />
								</svg>
							</button>
						</Tooltip>
					{/if}
				</div>
				<!-- What the bar under the canvas used to hold. It is here rather
				     than below the picture because every one of these acts on the
				     work being looked at; the fullscreen button stays last, at the
				     corner, so it keeps the position it has always had. -->
				<div class="canvas-corner-controls canvas-corner-right" onpointerdown={(event) => event.stopPropagation()}>
					{#if statusHashLabel}
						<Tooltip placement="top-left" text={statusHashCopied ? (isJapanese ? 'コピーしました' : 'Copied') : (isJapanese ? 'クリックでfull hashをコピーします' : 'Click to copy the full hash')}>
							<button
								type="button"
								class="canvas-icon-btn canvas-hash-btn"
								class:marked={statusHashCopied}
								aria-label={isJapanese ? 'full hash をコピー' : 'Copy the full hash'}
								onclick={onCopyStatusHash}
							>#</button>
						</Tooltip>
					{/if}
					<Tooltip placement="top-left" text={t().historyReplayTitle}>
						<button
							type="button"
							class="canvas-icon-btn canvas-replay-btn"
							disabled={replayDisabled}
							aria-label={t().historyReplay}
							onclick={onReplayCurrent}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M20 12a8 8 0 1 1-2.6-5.9" />
								<path d="M20 4v4h-4" />
							</svg>
						</button>
					</Tooltip>
					<Tooltip placement="top-left" text={isJapanese ? '選択中作品の生成情報を表示' : 'Show the provenance, prompts, and JSON of the chosen work'}>
						<button
							bind:this={generationInfoToggleEl}
							type="button"
							class="canvas-icon-btn canvas-provenance-btn"
							class:active={generationInfoOpen}
							disabled={!result && !allowEmptyOutputTabs}
							aria-expanded={generationInfoOpen}
							aria-label={isJapanese ? '生成情報' : 'Provenance'}
							onclick={onToggleGenerationInfo}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<circle cx="12" cy="12" r="8.5" />
								<path d="M12 11v5.5M12 7.8v.4" />
							</svg>
						</button>
					</Tooltip>
					<Tooltip placement="top-left" text={t().tooltipSaijikiToggle}>
						<button
							type="button"
							class="canvas-icon-btn canvas-saijiki-btn"
							data-saijiki-toggle
							aria-label={t().saijikiToggleBtn}
							onclick={onToggleSaijiki}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M5 5.5h5.5a1.5 1.5 0 0 1 1.5 1.5v11a1.2 1.2 0 0 0-1.2-1.2H5z" />
								<path d="M19 5.5h-5.5a1.5 1.5 0 0 0-1.5 1.5v11a1.2 1.2 0 0 1 1.2-1.2H19z" />
							</svg>
						</button>
					</Tooltip>
					<!-- One door for the three ways a work leaves: SVG, PNG, and the
					     share card. They were three buttons side by side, which said
					     three things where the reader wanted one. -->
					<div class="canvas-export" bind:this={exportWrapEl}>
						<Tooltip placement="top-left" text={exportCardOnly ? t().historyCardExport : t().exportLabel}>
							<button
								type="button"
								class="canvas-icon-btn canvas-export-btn"
								class:active={exportMenuOpen && !exportCardOnly}
								disabled={exportCardOnly ? (!currentHistoryId || cardExportBusy) : !result}
								aria-haspopup={exportCardOnly ? undefined : 'menu'}
								aria-expanded={exportCardOnly ? undefined : exportMenuOpen}
								aria-label={exportCardOnly ? t().historyCardExport : t().exportLabel}
								onclick={(e) => {
									e.stopPropagation();
									// One button, two jobs, decided by which tools the reader kept.
									// With the work tools gone there is nothing to choose between,
									// so opening a menu of one would be a door onto a door.
									if (exportCardOnly) onDownloadCard();
									else exportMenuOpen = !exportMenuOpen;
								}}
							>
								<svg class="download-icon" viewBox="0 0 24 24" aria-hidden="true">
									<path d="M12 3v11m0 0 4-4m-4 4-4-4M5 18h14" />
								</svg>
							</button>
						</Tooltip>
						{#if exportMenuOpen && !exportCardOnly}
							<div class="export-menu" role="menu">
								<div class="export-menu-group">
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
									<button onclick={() => { onDownloadSVG('display'); exportMenuOpen = false; }}>
										<span class="png-size">{t().svgExportDisplayName}</span>
										<span class="png-sub">{t().svgExportDisplaySub}</span>
									</button>
									<button onclick={() => { onDownloadSVG('editable'); exportMenuOpen = false; }}>
										<span class="png-size">{t().svgExportEditableName}</span>
										<span class="png-sub">{t().svgExportEditableSub}</span>
									</button>
									<button onclick={() => { onDownloadSVG('compat'); exportMenuOpen = false; }}>
										<span class="png-size">{t().svgExportCompatName}</span>
										<span class="png-sub">{t().svgExportCompatSub}</span>
									</button>
								</div>
								<div class="export-menu-group">
									<div class="export-menu-head">PNG</div>
									{#each pngTemplates as template (template.id)}
										<button onclick={() => { onDownloadPNG(template.y_px); exportMenuOpen = false; }}>
											<span class="png-size">{template.name}</span>
											<span class="png-sub">{pngTemplateDescription(template)}</span>
										</button>
									{/each}
								</div>
								<div class="export-menu-group">
									<button
										type="button"
										disabled={!currentHistoryId || cardExportBusy}
								onclick={() => { onDownloadCard(); exportMenuOpen = false; }}
									>
										<span class="png-size">{cardExportBusy ? t().cardExportBusy : t().historyCardExport}</span>
										<span class="png-sub">{t().tooltipCanvasDownloadCard}</span>
									</button>
								</div>
							</div>
						{/if}
					</div>
					<Tooltip placement="top-left" text={t().tooltipCanvasPresentation}>
						<button
							type="button"
							class="canvas-icon-btn canvas-presentation-btn"
							disabled={!result}
							aria-label={t().canvasPresentationOpen}
							onclick={(event) => {
								event.stopPropagation();
								onOpenPresentation();
							}}
						>
							<svg viewBox="0 0 24 24" aria-hidden="true">
								<path d="M8.5 4.5h-4v4M15.5 4.5h4v4M8.5 19.5h-4v-4M15.5 19.5h4v-4" />
								<path d="M8 8 4.5 4.5M16 8l3.5-3.5M8 16l-3.5 3.5M16 16l3.5 3.5" />
							</svg>
						</button>
					</Tooltip>
				</div>
				{#if instructionCaptionVisible && canShowInstructionCaption}
					<div class="instruction-caption" aria-live="polite"><CaptionText text={displayInstructionText} /></div>
				{/if}
</div>
			<div class="zoom-controls">
				<Tooltip text={t().tooltipCanvasZoomOut}>
					<button onclick={() => viewport.setZoom(viewport.zoom - 0.25)}>−</button>
				</Tooltip>
				<span class="zoom-pct">{Math.round(viewport.zoom * 100)}%</span>
				<Tooltip text={t().tooltipCanvasZoomIn}>
					<button onclick={() => viewport.setZoom(viewport.zoom + 0.25)}>＋</button>
				</Tooltip>
				<Tooltip text={t().tooltipCanvasZoomReset}>
					<button class="zoom-reset" onclick={() => viewport.fit()}>⊙</button>
				</Tooltip>
			</div>

<style>
	.unsaved-refinement-badge { position: absolute; top: 12px; left: 50%; transform: translateX(-50%); z-index: 5; padding: 5px 9px; border: 1px solid var(--border2); border-radius: 999px; background: color-mix(in srgb, var(--panel) 94%, transparent); color: var(--fg2); box-shadow: 0 2px 10px #0002; font-size: 11px; white-space: nowrap; }
	/* The stack owns the corner; each badge only paints itself, so a second one
	   sits under the first instead of on top of it. */
	.fallback-badges { position: absolute; top: 12px; right: 12px; z-index: 5; display: flex; flex-direction: column; align-items: flex-end; gap: 6px; }
	.interpret-fallback-badge, .compose-fallback-badge { padding: 5px 9px; border: 1px solid #c08a3e; border-radius: 999px; background: color-mix(in srgb, #f6e2bd 88%, transparent); color: #6b4410; box-shadow: 0 2px 10px #0002; font-size: 11px; white-space: nowrap; }
	:global(html[data-theme='dark']) .interpret-fallback-badge, :global(html[data-theme='dark']) .compose-fallback-badge { border-color: #d8a75c; background: color-mix(in srgb, #5a4318 88%, transparent); color: #f4dcb0; }
	.lineage-intermediate-notice { position: absolute; top: 48px; left: 50%; transform: translateX(-50%); z-index: 6; max-width: min(520px, calc(100% - 48px)); padding: 7px 10px; border-radius: var(--r); background: var(--tooltip-bg); color: var(--tooltip-fg); box-shadow: 0 4px 18px #0004; font-size: 11px; line-height: 1.45; text-align: center; }
	.canvas-content {
		position: relative;
		width: 100%;
		height: 100%;
		display: flex;
		align-items: center;
		justify-content: center;
		overflow: hidden;
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
	.canvas-box :global(> svg) { width: 100%; height: 100%; display: block; }
	/* The drawing arrives as an image now; it fills the box the same way the
	   inline SVG did, so zoom and pan keep working off the boxes around it. */
	.canvas-box > .canvas-art { width: 100%; height: 100%; display: block; }
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
		/* A Tooltip cannot escape its parent's stacking context. Keep the whole
		   button row above the caption so its bubbles do not pass behind it. */
		z-index: 13;
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
	/* Three of these are glyphs rather than drawn paths: the star and the
	   pencil are the marks the history manager already uses for the same two
	   flags, and the hash is the character the value itself starts with. */
	.canvas-star-btn, .canvas-revision-btn, .canvas-hash-btn {
		font-family: inherit;
		font-size: 15px;
		line-height: 1;
	}
	.canvas-hash-btn { font-weight: 600; }
	/* `marked` is a flag standing on the work, not a pressed button: it has to
	   read as on while the pointer is somewhere else entirely. */
	.canvas-star-btn.marked {
		color: var(--star-fg);
		border-color: var(--star-border);
		background: var(--star-bg);
	}
	.canvas-revision-btn.marked,
	.canvas-hash-btn.marked {
		color: var(--accent);
		border-color: var(--accent);
		background: var(--accent-light);
	}
	.canvas-export-btn .download-icon { width: 18px; height: 18px; }
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
		text-align: left;
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
	/* The export menu hangs off the corner controls, so it opens upward from a
	   button that sits at the bottom of the canvas. */
	.canvas-export { position: relative; display: inline-flex; }
	.export-menu {
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
	.export-menu > .export-menu-group > button {
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
	.export-menu-group:last-child > button:last-child { border-bottom: none; }
	.export-menu > .export-menu-group > button:hover:not(:disabled) { background: var(--bg); }
	.export-menu > .export-menu-group > button:disabled { opacity: .45; cursor: not-allowed; }
	/* The three ways out are one list, divided rather than stacked in three
	   boxes: a rule says "another kind" without spending the height a second
	   frame would. */
	.export-menu-group + .export-menu-group { border-top: 2px solid var(--border2); }
	.export-menu-head {
		padding: 7px 14px 3px;
		color: var(--fg3);
		font-size: 10px;
		font-weight: 600;
		letter-spacing: .08em;
	}
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
	@media (max-width: 720px) {
		.instruction-caption {
			left: 10%;
			right: 10%;
			bottom: 58px;
			font-size: 13px;
		}
	}
</style>
