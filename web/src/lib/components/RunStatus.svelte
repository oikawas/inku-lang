<script lang="ts">
	/**
	 * The single "drawing in progress" indicator.
	 *
	 * Every running operation (single draw, batch, demo, DDL editor, lineage
	 * edit, variations, model/language comparison, AI refinement) renders this
	 * component, so the mascot, the model line, the elapsed/token line and the
	 * stop button keep one shape and one set of dimensions.
	 *
	 * `variant="bar"` is a standalone block inside a panel. `variant="inline"`
	 * sits at the right end of an existing button row (dialog footers, the
	 * comparison panel heads) and therefore carries no frame of its own.
	 */
	import IncuMascot from './IncuMascot.svelte';
	import YuragiMascot from './YuragiMascot.svelte';
	import StopButton from './StopButton.svelte';
	import { t } from '$lib/i18n/index.svelte';
	import { getMascot } from '$lib/mascot.svelte';

	type Props = {
		label: string;
		variant?: 'bar' | 'inline';
		/** Interpretation-stage model. Shown together with `stage2Model`. */
		stage1Model?: string | null;
		/** Rendering-stage model. */
		stage2Model?: string | null;
		/** Single model name, used instead of the stage pair (comparison runs). */
		model?: string | null;
		elapsedMs?: number | null;
		/** Concurrent-job progress. Shown in the meta line when total > 1. */
		progressDone?: number | null;
		progressTotal?: number | null;
		tokensIn?: number | null;
		tokensOut?: number | null;
		stopLabel?: string;
		onStop?: (() => void) | null;
		children?: import('svelte').Snippet;
	};

	let {
		label,
		variant = 'bar',
		stage1Model = null,
		stage2Model = null,
		model = null,
		elapsedMs = null,
		progressDone = null,
		progressTotal = null,
		tokensIn = null,
		tokensOut = null,
		stopLabel,
		onStop = null,
		children
	}: Props = $props();

	const modelLine = $derived.by(() => {
		if (model) return model;
		if (stage1Model && stage2Model) {
			if (stage1Model === stage2Model) return stage1Model;
			return `${t().runStatusStage1} ${stage1Model} ／ ${t().runStatusStage2} ${stage2Model}`;
		}
		return stage1Model || stage2Model || '';
	});
	// The label is a single ellipsized line, so progress goes in the meta line
	// where it stays visible in narrow panels.
	const progressText = $derived(
		progressDone !== null && progressTotal !== null && progressTotal > 1
			? t().runStatusProgress(progressDone, progressTotal)
			: ''
	);
	const elapsedText = $derived(
		elapsedMs === null ? '' : t().runStatusElapsed((elapsedMs / 1000).toFixed(1))
	);
	const tokenText = $derived(
		t().runStatusTokens(
			tokensIn === null || tokensIn === undefined ? '-' : String(tokensIn),
			tokensOut === null || tokensOut === undefined ? '-' : String(tokensOut)
		)
	);
</script>

<div class="run-status" class:inline={variant === 'inline'} aria-live="polite">
	<div class="run-mascot">
		{#if getMascot() === 'yuragi'}<YuragiMascot />{:else}<IncuMascot />{/if}
	</div>
	<div class="run-info">
		<span class="run-label">{label}</span>
		{#if modelLine}<span class="run-model">{modelLine}</span>{/if}
		<span class="run-meta">
			{#if progressText}<span class="run-progress">{progressText}</span>{/if}
			{#if elapsedText}<span>{elapsedText}</span>{/if}
			<span>{tokenText}</span>
		</span>
	</div>
	{#if children}<div class="run-extra">{@render children()}</div>{/if}
	{#if onStop}<StopButton onclick={onStop}>{stopLabel ?? t().stopBtn}</StopButton>{/if}
</div>

<style>
	.run-status {
		display: flex;
		align-items: center;
		gap: 10px;
		min-height: 46px;
		padding: 6px 8px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		min-width: 0;
	}
	.run-status.inline {
		flex: 0 0 auto;
		margin-left: auto;
		min-height: 0;
		padding: 0;
		border: 0;
		background: transparent;
	}
	.run-mascot {
		flex: 0 0 auto;
		display: flex;
		align-items: center;
		justify-content: center;
	}
	.run-info {
		flex: 1 1 auto;
		min-width: 0;
		display: flex;
		flex-direction: column;
		gap: 2px;
	}
	.run-status.inline .run-info {
		flex: 0 0 auto;
		align-items: flex-end;
		text-align: right;
	}
	.run-label {
		font-size: 12px;
		font-weight: 500;
		color: var(--fg);
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
	}
	.run-model {
		font-size: 11px;
		color: var(--fg3);
		line-height: 1.35;
		overflow-wrap: anywhere;
	}
	.run-meta {
		display: flex;
		gap: 8px;
		font-size: 11px;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		white-space: nowrap;
	}
	.run-status.inline .run-meta {
		justify-content: flex-end;
	}
	.run-progress {
		color: var(--fg2);
		font-weight: 600;
	}
	.run-extra {
		flex: 0 0 auto;
		display: flex;
		align-items: center;
	}
	.run-status :global(.stop-btn) {
		flex: 0 0 auto;
		width: auto;
		min-width: 0;
		padding: 7px 14px;
		font-size: 13px;
		letter-spacing: 0.06em;
	}
</style>
