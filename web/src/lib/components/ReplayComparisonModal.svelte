<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		originalSvg: string;
		replayedSvg: string;
		recordedVersion: string | null;
		currentVersion: string | null;
		versionMessage: string | null;
		onClose: () => void;
	};

	let {
		originalSvg,
		replayedSvg,
		recordedVersion,
		currentVersion,
		versionMessage,
		onClose,
	}: Props = $props();
</script>

<svelte:window onkeydown={(event) => { if (event.key === 'Escape') onClose(); }} />

<div class="replay-layer">
	<div
		class="replay-backdrop"
		role="button"
		tabindex="0"
		aria-label={t().closeLabel}
		onclick={onClose}
		onkeydown={(event) => { if (event.key === 'Enter' || event.key === ' ') onClose(); }}
	></div>
	<div class="replay-dialog" role="dialog" aria-modal="true" aria-labelledby="replay-comparison-title" tabindex="-1">
		<header class="replay-header">
			<h2 id="replay-comparison-title">{t().replayComparisonTitle}</h2>
			<button type="button" class="ghost-btn" onclick={onClose}>{t().closeLabel}</button>
		</header>

		{#if versionMessage}
			<div class="version-message" role="status">{versionMessage}</div>
		{/if}

		<div class="comparison-grid">
			<article class="artwork-card">
				<header class="artwork-heading">
					<strong>{t().replayComparisonOriginal}</strong>
					<span>engine {recordedVersion ?? t().historyVersionNotRecorded}</span>
				</header>
				<div class="artwork-frame">{@html originalSvg}</div>
			</article>
			<article class="artwork-card">
				<header class="artwork-heading">
					<strong>{t().replayComparisonCurrent}</strong>
					<span>engine {currentVersion ?? t().historyVersionUnknown}</span>
				</header>
				<div class="artwork-frame">{@html replayedSvg}</div>
			</article>
		</div>
	</div>
</div>

<style>
	.replay-layer {
		position: fixed;
		inset: 0;
		z-index: 6000;
		display: flex;
		align-items: center;
		justify-content: center;
		padding: 20px;
	}
	.replay-backdrop { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.52); }
	.replay-dialog {
		position: relative;
		width: min(1120px, calc(100vw - 40px));
		max-height: calc(100vh - 40px);
		overflow: auto;
		box-sizing: border-box;
		padding: 18px;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		background: var(--panel);
		box-shadow: 0 16px 48px rgba(0, 0, 0, 0.28);
	}
	.replay-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
	.replay-header h2 { margin: 0; color: var(--fg); font-size: 16px; font-weight: 600; }
	.ghost-btn {
		padding: var(--btn-sm-padding);
		border: 1px solid var(--border2);
		border-radius: var(--btn-sm-radius);
		background: var(--panel);
		color: var(--fg2);
		font: inherit;
		font-size: var(--btn-sm-font-size);
		cursor: pointer;
	}
	.ghost-btn:hover { background: var(--bg2); }
	.version-message { margin-top: 14px; padding: 9px 12px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--bg2); color: var(--fg); font-size: 12px; line-height: 1.5; text-align: center; }
	.comparison-grid { display: grid; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); gap: 14px; margin-top: 14px; }
	.artwork-card { min-width: 0; overflow: hidden; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel2); }
	.artwork-heading { display: flex; align-items: baseline; justify-content: space-between; gap: 12px; padding: 9px 11px; border-bottom: 1px solid var(--border2); color: var(--fg); }
	.artwork-heading strong { font-size: 13px; }
	.artwork-heading span { color: var(--fg2); font-size: 12px; font-variant-numeric: tabular-nums; }
	.artwork-frame { display: grid; min-height: 360px; place-items: center; padding: 12px; overflow: auto; background: var(--canvas-paper); }
	.artwork-frame :global(svg) { display: block; width: auto; max-width: 100%; height: auto; max-height: min(62vh, 620px); }
	@media (max-width: 760px) {
		.replay-layer { padding: 10px; }
		.replay-dialog { width: calc(100vw - 20px); max-height: calc(100vh - 20px); padding: 14px; }
		.comparison-grid { grid-template-columns: 1fr; }
		.artwork-frame { min-height: 260px; }
	}
</style>
