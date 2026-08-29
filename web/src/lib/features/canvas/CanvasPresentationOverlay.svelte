<script lang="ts">
	import Tooltip from '$lib/components/Tooltip.svelte';
	import CaptionText from '$lib/components/CaptionText.svelte';
	import { t } from '$lib/i18n/index.svelte';

	export type PresentationWorkMark = {
		id?: string | null;
		starred?: boolean | null;
	};

	type Props = {
		artworkUrl: string | null;
		instructionCaptionVisible: boolean;
		canShowInstructionCaption: boolean;
		displayInstructionText: string;
		interactionLocked: boolean;
		navNewerDisabled: boolean;
		navLatestDisabled: boolean;
		navOlderDisabled: boolean;
		historyTotal: number;
		navPos: number;
		workMark: PresentationWorkMark | null;
		onGotoNext: () => void | Promise<void>;
		onGotoLatest: () => void | Promise<void>;
		onGotoPrev: () => void | Promise<void>;
		onToggleStar: (event: Event) => void | Promise<void>;
		onToggleCaption: () => void | Promise<void>;
		onClose: () => void;
	};

	let {
		artworkUrl,
		instructionCaptionVisible,
		canShowInstructionCaption,
		displayInstructionText,
		interactionLocked,
		navNewerDisabled,
		navLatestDisabled,
		navOlderDisabled,
		historyTotal,
		navPos,
		workMark,
		onGotoNext,
		onGotoLatest,
		onGotoPrev,
		onToggleStar,
		onToggleCaption,
		onClose
	}: Props = $props();
</script>

<div class="presentation-overlay" role="dialog" aria-modal="true" aria-label={t().canvasPresentationTitle}>
	<div class="presentation-stage">
		<div class="presentation-art">
			<!-- The same work as the canvas, shown larger, so the same reason applies. -->
			{#if artworkUrl}
				<img class="canvas-art" src={artworkUrl} alt="" />
			{/if}
		</div>
		{#if instructionCaptionVisible && canShowInstructionCaption}
			<div class="presentation-caption"><CaptionText text={displayInstructionText} /></div>
		{/if}
	</div>
	<div class="presentation-controls" aria-label={t().canvasPresentationControls}>
		<Tooltip text={t().tooltipCanvasNavNewer}>
			<button type="button" class="presentation-icon-btn" onclick={onGotoNext} disabled={interactionLocked || navNewerDisabled} aria-label={t().tooltipCanvasNavNewer}>
				‹
			</button>
		</Tooltip>
		<Tooltip text={t().tooltipCanvasNavLatest}>
			<button type="button" class="presentation-text-btn" onclick={onGotoLatest} disabled={interactionLocked || navLatestDisabled}>{t().historyLatest}</button>
		</Tooltip>
		<Tooltip text={t().tooltipCanvasNavOlder}>
			<button type="button" class="presentation-icon-btn" onclick={onGotoPrev} disabled={interactionLocked || navOlderDisabled} aria-label={t().tooltipCanvasNavOlder}>
				›
			</button>
		</Tooltip>
		<span class="presentation-counter">{historyTotal > 0 ? `${navPos} / ${historyTotal}` : ''}</span>
		<Tooltip text={workMark?.starred ? t().starOn : t().starOff}>
			<button
				type="button"
				class="presentation-icon-btn presentation-star-btn"
				class:starred={!!workMark?.starred}
				disabled={!workMark?.id}
				onclick={onToggleStar}
				aria-label={workMark?.starred ? t().starOn : t().starOff}
			>
				★
			</button>
		</Tooltip>
		<Tooltip text={t().canvasCaptionToggle}>
			<button
				type="button"
				class="presentation-icon-btn"
				class:active={instructionCaptionVisible}
				disabled={!canShowInstructionCaption}
				onclick={onToggleCaption}
				aria-label={t().canvasCaptionToggle}
			>
				<svg viewBox="0 0 24 24" aria-hidden="true">
					<rect x="3.5" y="5.5" width="17" height="13" rx="2.5" />
					<path d="M7.5 10.5h4.5M14.5 10.5h2M7.5 14h3M13 14h3.5" />
				</svg>
			</button>
		</Tooltip>
		<Tooltip text={t().canvasPresentationClose}>
			<button type="button" class="presentation-icon-btn" onclick={onClose} aria-label={t().canvasPresentationClose}>
				<svg viewBox="0 0 24 24" aria-hidden="true">
					<path d="M6 6l12 12M18 6 6 18" />
				</svg>
			</button>
		</Tooltip>
	</div>
</div>

<style>
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
	.presentation-stage { position: relative; min-width: 0; min-height: 0; display: flex; align-items: center; justify-content: center; overflow: hidden; }
	.presentation-art { width: 100%; height: 100%; display: flex; align-items: center; justify-content: center; }
	.presentation-art :global(svg),
	.presentation-art .canvas-art { max-width: 100%; max-height: 100%; width: auto; height: auto; display: block; box-shadow: 0 10px 42px rgba(0,0,0,0.42); }
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
	.presentation-icon-btn { width: 34px; border-radius: 50%; font-size: 19px; padding: 0; }
	.presentation-text-btn { border-radius: 999px; font-size: 12px; padding: 0 12px; white-space: nowrap; }
	.presentation-icon-btn:hover:not(:disabled),
	.presentation-text-btn:hover:not(:disabled),
	.presentation-icon-btn.active { background: rgba(255,255,255,0.16); }
	.presentation-star-btn { color: rgba(255,253,248,0.62); font-size: 17px; }
	.presentation-star-btn.starred { color: #ffd45c; border-color: rgba(255,212,92,0.62); background: rgba(255,212,92,0.14); }
	.presentation-icon-btn:disabled,
	.presentation-text-btn:disabled { opacity: 0.35; cursor: not-allowed; }
	.presentation-icon-btn svg { width: 18px; height: 18px; fill: none; stroke: currentColor; stroke-width: 2; stroke-linecap: round; stroke-linejoin: round; }
	.presentation-counter { min-width: 44px; padding: 0 6px; color: rgba(255,253,248,0.72); font-size: 12px; font-variant-numeric: tabular-nums; text-align: center; white-space: nowrap; }

	@media (max-width: 720px) {
		.presentation-overlay { padding: 12px; }
		.presentation-controls { width: 100%; box-sizing: border-box; border-radius: 12px; flex-wrap: wrap; }
	}
</style>
