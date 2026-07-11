<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import DdlEditPanel from './DdlEditPanel.svelte';
	import PaintButton from './PaintButton.svelte';
	import Tooltip from './Tooltip.svelte';

	type SaijikiPreview = {
		categoryKey: string;
		word: string;
		canonicalWord: string;
		effect: string;
		example: string;
		svg: string;
	};

	type Props = {
		ddl: string;
		ddlHighlighted: string;
		ddlTextareaEl: HTMLTextAreaElement | null;
		ddlHighlightEl: HTMLDivElement | null;
		ddlFocused: boolean;
		reloading: boolean;
		reloadError: string | null;
		loading: boolean;
		generationDisabled: boolean;
		liveMs: number;
		tokenSummary: string;
		showKiwi: boolean;
		autoRepairEnabled: boolean;
		activeSaijikiPreview: SaijikiPreview | null;
		onToggleSaijiki: () => void;
		onInsertWord: (word: string) => void;
		previewForWord: (categoryKey: string, canonicalWord: string, word: string) => SaijikiPreview;
		onRememberSelection: () => void;
		onSyncHighlightScroll: () => void;
		onReplay: () => void | Promise<void>;
		onStopReplay: () => void;
	};

	let {
		ddl = $bindable(''),
		ddlHighlighted,
		ddlTextareaEl = $bindable(null),
		ddlHighlightEl = $bindable(null),
		ddlFocused = $bindable(false),
		reloading,
		reloadError,
		loading,
		generationDisabled,
		liveMs,
		tokenSummary,
		showKiwi,
		autoRepairEnabled = $bindable(true),
		activeSaijikiPreview = $bindable(),
		onToggleSaijiki,
		onInsertWord,
		previewForWord,
		onRememberSelection,
		onSyncHighlightScroll,
		onReplay,
		onStopReplay,
	}: Props = $props();
</script>

<section class="panel-section">
	<div class="section-head">
		<span class="section-label">{t().ddlLabel}</span>
	</div>
	<DdlEditPanel
		bind:ddl
		{ddlHighlighted}
		bind:ddlTextareaEl
		bind:ddlHighlightEl
		bind:ddlFocused
		{reloading}
		{reloadError}
		{loading}
		{liveMs}
		{tokenSummary}
		{showKiwi}
		bind:autoRepairEnabled
		bind:activeSaijikiPreview
		{onToggleSaijiki}
		{onInsertWord}
		{previewForWord}
		{onStopReplay}
		onRememberSelection={onRememberSelection}
		onSyncHighlightScroll={onSyncHighlightScroll}
		onReplay={onReplay}
	/>
	{#if !reloading && !loading}
		<Tooltip placement="top" text={t().tooltipDdlPaint}>
			<PaintButton onclick={onReplay} disabled={!ddl.trim() || generationDisabled}>{t().ddlPaintButton}</PaintButton>
		</Tooltip>
	{/if}
</section>

<style>
	.panel-section { display: flex; flex-direction: column; gap: 6px; }
	.panel-section > :global(.tooltip-wrap) { width: 100%; }
	.section-head {
		display: flex;
		justify-content: space-between;
		align-items: center;
	}
	.section-label {
		font-size: 10px;
		font-weight: 500;
		letter-spacing: 0.08em;
		color: var(--fg3);
		text-transform: uppercase;
	}
</style>
