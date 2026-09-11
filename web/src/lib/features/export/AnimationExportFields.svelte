<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import type { AnimationExportSettings } from '$lib/animationExport';

	type Props = {
		settings: AnimationExportSettings;
		disabled?: boolean;
	};

	let { settings = $bindable(), disabled = false }: Props = $props();
</script>

<div class="animation-settings-grid">
	<label>
		<span>{t().settingsAnimationFormat}</span>
		<select value={settings.format} {disabled} onchange={(event) => (settings = { ...settings, format: event.currentTarget.value as AnimationExportSettings["format"] })}>
			<option value="apng">{t().animationFormatApng}</option>
			<option value="gif">{t().animationFormatGif}</option>
		</select>
	</label>
	<label>
		<span>{t().settingsAnimationPattern}</span>
		<select value={settings.pattern} {disabled} onchange={(event) => (settings = { ...settings, pattern: event.currentTarget.value as AnimationExportSettings["pattern"] })}>
			<option value="cut">{t().animationPatternCut}</option>
			<option value="crossfade">{t().animationPatternCrossfade}</option>
			<option value="fade_white">{t().animationPatternFadeWhite}</option>
			<option value="slide">{t().animationPatternSlide}</option>
		</select>
	</label>
	<label>
		<span>{t().settingsAnimationHold}</span>
		<input type="number" min="0.1" max="30" step="0.1" value={settings.holdSeconds} {disabled} onchange={(event) => (settings = { ...settings, holdSeconds: Math.max(0.1, Math.min(30, Number(event.currentTarget.value) || 1)) })} />
		<small>{t().settingsAnimationHoldHint}</small>
	</label>
	<label>
		<span>{t().settingsAnimationResolution}</span>
		<select value={settings.resolution} {disabled} onchange={(event) => (settings = { ...settings, resolution: event.currentTarget.value as AnimationExportSettings["resolution"] })}>
			<option value="150">{t().animationResolution150}</option>
			<option value="300">{t().animationResolution300}</option>
			<option value="500">{t().animationResolution500}</option>
			<option value="1k">{t().animationResolution1k}</option>
			<option value="4k">{t().animationResolution4k}</option>
			<option value="8k">{t().animationResolution8k}</option>
			<option value="custom">{t().animationResolutionCustom}</option>
		</select>
		{#if settings.resolution === "custom"}
			<input
				type="number"
				min="64"
				max="12000"
				step="1"
				value={settings.customHeight}
				aria-label={t().animationCustomHeight}
				{disabled}
				onchange={(event) => (settings = { ...settings, customHeight: Math.max(64, Math.min(12000, Math.round(Number(event.currentTarget.value) || 720))) })}
			/>
			<small>{t().animationCustomHeight}</small>
		{/if}
	</label>
</div>

<style>
	.animation-settings-grid {
		display: grid;
		grid-template-columns: repeat(2, minmax(0, 1fr));
		gap: 10px;
		margin-top: 10px;
	}
	.animation-settings-grid label { display: flex; min-width: 0; flex-direction: column; gap: 5px; color: var(--fg2); font-size: 11px; }
	.animation-settings-grid select,
	.animation-settings-grid input {
		min-width: 0;
		padding: 6px 8px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg);
		font: inherit;
	}
	.animation-settings-grid small { color: var(--fg3); font-size: 10px; }
	@media (max-width: 720px) { .animation-settings-grid { grid-template-columns: 1fr; } }
</style>
