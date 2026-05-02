<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import DdlEditPanel from './DdlEditPanel.svelte';
	import PaintButton from './PaintButton.svelte';

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
		liveMs: number;
		tokenSummary: string;
		showKiwi: boolean;
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
		liveMs,
		tokenSummary,
		showKiwi,
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
		<div class="section-actions">
			<button class="ghost-btn" onclick={onToggleSaijiki}>{t().saijikiToggleBtn}</button>
		</div>
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
		bind:activeSaijikiPreview
		{onInsertWord}
		{previewForWord}
		{onStopReplay}
		onRememberSelection={onRememberSelection}
		onSyncHighlightScroll={onSyncHighlightScroll}
		onReplay={onReplay}
	/>
	{#if !reloading && !loading}
		<PaintButton onclick={onReplay} disabled={!ddl}>{t().ddlPaintButton}</PaintButton>
	{/if}
</section>

<style>
	.panel-section { display: flex; flex-direction: column; gap: 6px; }
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
	.section-actions {
		display: flex;
		gap: 5px;
	}
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
</style>
