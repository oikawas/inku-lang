<script lang="ts">
	import Tooltip from './Tooltip.svelte';
	import type { ResolvedInstructionLang } from '$lib/instructionLang';
	import { t } from '$lib/i18n/index.svelte';
	import { hasDdlBody } from '$lib/ddl-source';
	import DdlEditor from './DdlEditor.svelte';
	import type { RangeEditorStatus } from '$lib/features/ddl-editor/codemirror-ranges';
	import type { PluginEntry, PreviewForPlugin, PreviewForWord } from '$lib/features/ddl-editor/types';
	import { scanNumericRanges, type CompositionRange, type RangePreview } from '$lib/composition-ranges';

	type Props = {
		/** The single source used for display, editing, and replay. */
		ddl: string;
		savedDdl?: string | null;
		onConfirmDiscard?: (run: () => void, cancel: () => void) => void;
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
		ranges?: CompositionRange[];
		workKey?: unknown;
		onDdlChange?: ((ddl: string) => void) | null;
		onRangePreview?: ((preview: RangePreview | null) => void) | null;
		pluginEntries?: PluginEntry[];
		previewForWord: PreviewForWord;
		previewForPlugin: PreviewForPlugin;
	};

	let { ddl, savedDdl = null, onConfirmDiscard, label, onEdit = null, editDisabled = false, onPaint = null, paintDisabled = false, runStatus = null, lang = null, ranges = [], workKey = null, onDdlChange = null, onRangePreview = null, pluginEntries = [], previewForWord, previewForPlugin }: Props = $props();
	let editor = $state<DdlEditor | null>(null);
	let rangeStatus = $state<RangeEditorStatus>({ preview: null, invalid: false, composing: false });

	const primaryLabel = $derived(lang ? t().ddlLabelIn(lang) : label);
	const readOnly = $derived(editDisabled || !onDdlChange);
	const invalidSource = $derived(rangeStatus.invalid || scanNumericRanges(ddl).some((range) => !range.bounds));
	const paintBlocked = $derived(paintDisabled || !hasDdlBody(ddl) || invalidSource || rangeStatus.composing);

	function updateRangeStatus(status: RangeEditorStatus): void {
		rangeStatus = status;
		onRangePreview?.(status.preview);
	}
	export function insertWord(word: string): void { if (!readOnly) editor?.insertWord(word); }
	function canDiscardEdits(): boolean {
		return savedDdl !== null && !!onConfirmDiscard && !readOnly && !paintDisabled && !rangeStatus.composing && ddl !== savedDdl;
	}
	function requestDiscardEdits(): void {
		const target = editor, original = savedDdl, targetWork = workKey;
		if (!canDiscardEdits() || !target || original === null) return;
		onConfirmDiscard?.(() => {
			if (!canDiscardEdits() || editor !== target || workKey !== targetWork || savedDdl !== original) return;
			target.replaceValueWithHistory(original);
		}, () => { if (editor === target && workKey === targetWork) target.focus(); });
	}
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
	<div class="ddl-viewer-body">
		{#key workKey}
			<DdlEditor
				bind:this={editor}
				value={ddl}
				isJapanese={t().code === 'ja'}
				disabled={readOnly}
				compact
				{ranges}
				{pluginEntries}
				{previewForWord}
				{previewForPlugin}
				onChange={onDdlChange ?? undefined}
				onRanges={updateRangeStatus}
			/>
		{/key}
	</div>
	{#if invalidSource}<div class="ddl-range-error" role="status">{t().ddlRangeInvalid}</div>{/if}
	{#if onPaint || (savedDdl !== null && onConfirmDiscard)}
		<div class="ddl-viewer-actions">
			{#if savedDdl !== null && onConfirmDiscard}
				<button class="ghost-btn" type="button" disabled={!canDiscardEdits()} onclick={requestDiscardEdits}>{t().ddlDiscardEdits}</button>
			{/if}
			{#if onPaint}
				<Tooltip placement="left" text={t().tooltipDdlPaint}>
					<button class="ghost-btn" type="button" disabled={paintBlocked} onclick={() => onPaint?.()}>{t().replayFromDdlButton}</button>
				</Tooltip>
			{/if}
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
		flex-wrap: wrap;
		gap: 8px;
		justify-content: flex-end;
	}
	.ddl-range-error { color: var(--error); font-size: var(--ui-font-size-12); }
</style>
