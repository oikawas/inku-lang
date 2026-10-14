<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import { svgImage } from '$lib/svgImage';

	type Props = {
		originalSvg: string;
		replayedSvg: string;
		recordedVersion: string | null;
		currentVersion: string | null;
		versionMessage: string | null;
		provisionalSeed: number | null;
		canSave: boolean;
		saving: boolean;
		saved: boolean;
		saveError: string | null;
		onSaveChild: () => void;
		onClose: () => void;
	};

	let {
		originalSvg,
		replayedSvg,
		recordedVersion,
		currentVersion,
		versionMessage,
		provisionalSeed,
		canSave,
		saving,
		saved,
		saveError,
		onSaveChild,
		onClose,
	}: Props = $props();

	function close() {
		if (!saving) onClose();
	}
</script>

<svelte:window onkeydown={(event) => { if (event.key === 'Escape') close(); }} />

<div class="replay-layer">
	<div
		class="replay-backdrop"
		role="button"
		tabindex="0"
		aria-label={t().closeLabel}
		onclick={close}
		onkeydown={(event) => { if (event.key === 'Enter' || event.key === ' ') close(); }}
	></div>
	<div class="replay-dialog" role="dialog" aria-modal="true" aria-labelledby="replay-comparison-title" tabindex="-1">
		<header class="replay-header">
			<h2 id="replay-comparison-title">{t().replayComparisonTitle}</h2>
			<button type="button" class="ghost-btn" onclick={close} disabled={saving}>{t().closeLabel}</button>
		</header>

		{#if provisionalSeed !== null}
			<div class="version-message provisional-seed-message" role="status">{t().replayComparisonProvisionalSeed(provisionalSeed)}</div>
		{/if}
		{#if versionMessage}
			<div class="version-message" role="status">{versionMessage}</div>
		{/if}

		<div class="comparison-grid">
			<article class="artwork-card">
				<header class="artwork-heading">
					<strong>{t().replayComparisonOriginal}</strong>
					<span>engine {recordedVersion ?? t().historyVersionNotRecorded}</span>
				</header>
				<div class="artwork-frame"><img use:svgImage={originalSvg} alt="" /></div>
			</article>
			<article class="artwork-card">
				<header class="artwork-heading">
					<strong>{t().replayComparisonCurrent}</strong>
					<span>engine {currentVersion ?? t().historyVersionUnknown}</span>
				</header>
				<div class="artwork-frame"><img use:svgImage={replayedSvg} alt="" /></div>
			</article>
		</div>
		<footer class="replay-actions">
			{#if saveError}
				<p class="save-message" role="alert">{saveError}</p>
			{:else if saved}
				<p class="save-message" role="status">{t().replayComparisonSaved}</p>
			{/if}
			<button type="button" class="save-child-btn" onclick={onSaveChild} disabled={!canSave || saving || saved}>
				{saving ? t().replayComparisonSaving : t().replayComparisonSaveChild}
			</button>
		</footer>
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
		padding: 0;
	}
	.replay-backdrop { position: absolute; inset: 0; background: rgba(0, 0, 0, 0.52); }
	.replay-dialog {
		position: relative;
		width: 100%;
		height: 100%;
		min-height: 0;
		display: flex;
		flex-direction: column;
		overflow: hidden;
		box-sizing: border-box;
		padding: 18px;
		border: 0;
		border-radius: 0;
		background: var(--panel);
		box-shadow: 0 16px 48px rgba(0, 0, 0, 0.28);
	}
	.replay-header { display: flex; flex-shrink: 0; align-items: center; justify-content: space-between; gap: 16px; }
	.replay-header h2 { margin: 0; color: var(--fg); font-size: var(--ui-font-size-16); font-weight: 600; }
	.replay-header button { flex-shrink: 0; white-space: nowrap; }
	.version-message { flex-shrink: 0; margin-top: 14px; padding: 9px 12px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--bg2); color: var(--fg); font-size: var(--ui-font-size-12); line-height: 1.5; text-align: center; }
	.comparison-grid { display: grid; flex: 1; min-height: 0; grid-template-columns: minmax(0, 1fr) minmax(0, 1fr); grid-template-rows: minmax(0, 1fr); gap: 14px; margin-top: 14px; }
	.artwork-card { display: flex; flex-direction: column; min-width: 0; min-height: 0; overflow: hidden; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel2); }
	.artwork-heading { display: flex; flex-shrink: 0; align-items: baseline; justify-content: space-between; gap: 12px; padding: 9px 11px; border-bottom: 1px solid var(--border2); color: var(--fg); }
	.artwork-heading strong { font-size: var(--ui-font-size-13); }
	.artwork-heading span { color: var(--fg2); font-size: var(--ui-font-size-12); font-variant-numeric: tabular-nums; }
	.artwork-frame { display: flex; flex: 1; min-height: 0; align-items: center; justify-content: center; padding: 12px; overflow: hidden; background: var(--canvas-paper); }
	.artwork-frame img { display: block; width: 100%; height: 100%; object-fit: contain; }
	.replay-actions { display: flex; flex-shrink: 0; align-items: center; justify-content: flex-end; gap: 14px; margin-top: 14px; }
	.save-message { margin: 0; color: var(--fg); font-size: var(--ui-font-size-13); }
	.save-child-btn { flex-shrink: 0; border: 1px solid var(--border2); border-radius: var(--btn-sm-radius); padding: var(--btn-sm-padding); background: var(--action-bg); color: var(--action-fg); font-size: var(--btn-sm-font-size); cursor: pointer; }
	.save-child-btn:hover:not(:disabled) { background: var(--action-hover); }
	.save-child-btn:disabled { opacity: 0.55; cursor: default; }
	@media (max-width: 760px) {
		.replay-dialog { padding: 14px; }
		.comparison-grid { grid-template-columns: 1fr; grid-template-rows: repeat(2, minmax(0, 1fr)); gap: 10px; }
		.artwork-frame { padding: 8px; }
		.replay-actions { flex-wrap: wrap; gap: 8px; }
	}
</style>
