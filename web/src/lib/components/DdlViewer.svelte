<script lang="ts">
	import { highlightDDL } from '$lib/highlight';
	import Tooltip from './Tooltip.svelte';
	import type { ResolvedInstructionLang } from '$lib/instructionLang';
	import { t } from '$lib/i18n/index.svelte';
	import { hasDdlBody } from '$lib/ddl-source';

	type Props = {
		/** The single source used for display, editing, and replay. */
		ddl: string;
		label: string;
		onEdit?: (() => void) | null;
		editDisabled?: boolean;
		/** Perform the shown DDL again through Stage 2. Omitted = no button. */
		onPaint?: (() => void) | null;
		/** Set by the caller while a run is in flight; empty DDL disables on its own. */
		paintDisabled?: boolean;
		/** Status + stop panel for the run this button started. Sits under the button. */
		runStatus?: import('svelte').Snippet | null;
		/** The language the DDL is read in; it names the heading. Omitted = `label`. */
		lang?: ResolvedInstructionLang | null;
	};

	let { ddl, label, onEdit = null, editDisabled = false, onPaint = null, paintDisabled = false, runStatus = null, lang = null }: Props = $props();

	const primaryLabel = $derived(lang ? t().ddlLabelIn(lang) : label);
	const highlighted = $derived(highlightDDL(ddl));
	const paintBlocked = $derived(paintDisabled || !hasDdlBody(ddl));
</script>

<div class="ddl-viewer">
	<div class="ddl-viewer-head">
		<!-- The slot, not the label, pushes the buttons right: the note wraps the label. -->
		<span class="ddl-viewer-label-slot">
			{#if lang}
				<!-- The note opens up and to the right of the heading's start: the
				     panel clips it at its bottom edge and must not widen. -->
				<Tooltip placement="top-right" text={t().tooltipDdlLang}>
					<span class="ddl-viewer-label">{primaryLabel}</span>
				</Tooltip>
			{:else}
				<span class="ddl-viewer-label">{primaryLabel}</span>
			{/if}
		</span>
		{#if onEdit}
			<Tooltip placement="left" text={t().tooltipDdlEdit}>
				<button class="ghost-btn" type="button" disabled={editDisabled} onclick={() => onEdit?.()}>{t().ddlEditButton}</button>
			</Tooltip>
		{/if}
	</div>
	<div class="ddl-viewer-body ddl-highlight">{@html highlighted}</div>
	{#if onPaint}
		<div class="ddl-viewer-actions">
			<Tooltip placement="left" text={t().tooltipDdlPaint}>
				<button class="ghost-btn" type="button" disabled={paintBlocked} onclick={() => onPaint?.()}>{t().replayFromDdlButton}</button>
			</Tooltip>
		</div>
	{/if}
	{#if runStatus}{@render runStatus()}{/if}
</div>

<style>
	.ddl-viewer {
		display: flex;
		flex-direction: column;
		gap: 8px;
		min-width: 0;
	}
	.ddl-viewer-head {
		display: flex;
		flex-wrap: wrap;
		align-items: center;
		gap: 8px;
	}
	.ddl-viewer-label-slot {
		margin-right: auto;
	}
	.ddl-viewer-label {
		font-size: var(--ui-font-size-12);
		font-weight: 600;
		color: var(--fg2);
	}
	.ddl-viewer-body {
		padding: 2px 0 2px 12px;
		border-left: 2px solid var(--border2);
		background: transparent;
		color: var(--fg);
		font-family: inherit;
		font-size: var(--ui-font-size-14);
		line-height: 1.78;
		white-space: pre-wrap;
		word-break: break-word;
		tab-size: 4;
		overflow-x: auto;
	}
	.ddl-viewer-actions {
		display: flex;
		justify-content: flex-end;
	}
</style>
