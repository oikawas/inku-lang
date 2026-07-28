<script lang="ts">
	import { highlightDDL } from '$lib/highlight';
	import Tooltip from './Tooltip.svelte';
	import PaintButton from './PaintButton.svelte';
	import { t } from '$lib/i18n/index.svelte';

	type Props = {
		/** Input-side DDL: the Stage 1 output, or the DDL the user wrote. */
		ddl: string;
		/** Stage 1.5 output = what Stage 2 actually received. */
		expandedDdl?: string | null;
		label: string;
		expandedLabel: string;
		/** Perform the shown DDL again through Stage 2. Omitted = no button. */
		onPaint?: (() => void) | null;
		/** Set by the caller while a run is in flight; empty DDL disables on its own. */
		paintDisabled?: boolean;
		/** Status + stop panel for the run this button started. Sits under the button. */
		runStatus?: import('svelte').Snippet | null;
	};

	let { ddl, expandedDdl = null, label, expandedLabel, onPaint = null, paintDisabled = false, runStatus = null }: Props = $props();

	// Artworks saved before v1.98 have no input-side DDL: their single stored text
	// is the expanded one. Show it in the main slot and rename the label so the
	// panel never claims to show something it does not have.
	// LEGACY-ONLY: this branch exists for pre-v1.98 rows in the development
	// database and can be deleted once those artworks are gone.
	const legacyExpandedOnly = $derived(!ddl && !!expandedDdl);
	const primary = $derived(legacyExpandedOnly ? (expandedDdl as string) : ddl);
	const primaryLabel = $derived(legacyExpandedOnly ? expandedLabel : label);
	const showExpanded = $derived(!legacyExpandedOnly && !!expandedDdl && expandedDdl !== ddl);
	const highlighted = $derived(highlightDDL(primary));
	const expandedHighlighted = $derived(highlightDDL(expandedDdl ?? ''));
	// The legacy branch shows an expanded DDL the caller cannot re-perform, so the
	// button follows the input-side text the caller actually holds.
	const paintBlocked = $derived(paintDisabled || !ddl.trim());
	let expandedOpen = $state(false);
</script>

<div class="ddl-viewer">
	<div class="ddl-viewer-head">
		<span class="ddl-viewer-label">{primaryLabel}</span>
	</div>
	<div class="ddl-viewer-body ddl-highlight">{@html highlighted}</div>
	{#if onPaint}
		<div class="ddl-viewer-actions">
			<Tooltip placement="left" text={t().tooltipDdlPaint}>
				<PaintButton icon={false} block={false} disabled={paintBlocked} onclick={() => onPaint?.()}>{t().replayFromDdlButton}</PaintButton>
			</Tooltip>
		</div>
	{/if}
	{#if runStatus}{@render runStatus()}{/if}
	{#if showExpanded}
		<div class="ddl-expanded">
			<Tooltip placement="right" text={t().tooltipDdlExpandedToggle}>
				<button class="ddl-expanded-toggle" type="button" onclick={() => (expandedOpen = !expandedOpen)}>
					<span class="ddl-expanded-arrow" class:open={expandedOpen}>▶</span>
					<span>{expandedLabel}</span>
				</button>
			</Tooltip>
			{#if expandedOpen}
				<div class="ddl-viewer-body ddl-highlight">{@html expandedHighlighted}</div>
			{/if}
		</div>
	{/if}
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
		align-items: center;
		gap: 8px;
	}
	.ddl-viewer-label {
		margin-right: auto;
		font-size: 12px;
		font-weight: 600;
		letter-spacing: 0.04em;
		color: var(--fg2);
	}
	.ddl-viewer-body {
		padding: 2px 0 2px 12px;
		border-left: 2px solid var(--border2);
		background: transparent;
		color: var(--fg);
		font-family: inherit;
		font-size: 13px;
		line-height: 1.78;
		white-space: pre-wrap;
		word-break: break-word;
		tab-size: 4;
		overflow-x: auto;
	}
	.ddl-viewer-actions {
		display: flex;
		justify-content: flex-end;
		margin-top: -2px;
	}
	.ddl-expanded {
		display: flex;
		flex-direction: column;
		gap: 6px;
	}
	.ddl-expanded-toggle {
		display: flex;
		align-items: center;
		gap: 5px;
		padding: 2px 0;
		border: 0;
		background: none;
		color: var(--fg3);
		font-family: inherit;
		font-size: 11px;
		cursor: pointer;
		text-align: left;
	}
	.ddl-expanded-arrow {
		display: inline-block;
		font-size: 8px;
		transition: transform 0.15s ease;
	}
	.ddl-expanded-arrow.open {
		transform: rotate(90deg);
	}
</style>
