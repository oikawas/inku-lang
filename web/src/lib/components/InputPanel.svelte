<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import LabelHighlight from './LabelHighlight.svelte';
	import { pipelineDescription } from '$lib/description-labels';
	import Tooltip from './Tooltip.svelte';
	import BatchPanel from './BatchPanel.svelte';
	import CanvasAspectPlugin from './CanvasAspectPlugin.svelte';
	import SketchSelect from './SketchSelect.svelte';
	import { type SketchMode } from '$lib/sketch';
	import { wildSettings } from '$lib/features/wild/settings.svelte';
	import PaintButton from './PaintButton.svelte';
	import RunStatus from './RunStatus.svelte';
	import type { CanvasAspectId, CanvasAspectOption } from '$lib/plugins/system/canvas-aspect';
	import type { ProviderAttemptCount } from '$lib/paintStream';

	type BatchFailure = {
		line: number;
		input: string;
		message: string;
	};
	type BatchFailureReport = {
		success: number;
		total: number;
		failures: BatchFailure[];
	};
	type Props = {
		inputMode: 'single' | 'batch';
		input: string;
		batchInput: string;
		lineNumbersText: string;
		batchNonEmpty: number;
		batchRunning: boolean;
		singleRunning: boolean;
		descriptionLocked: boolean;
		/** The run shows its status elsewhere (the instruction sheet draws its own). */
		hideRunStatus?: boolean;
		runTokensIn: number | null;
		runTokensOut: number | null;
		runAttempt?: ProviderAttemptCount | null;
		singleDdlReady: boolean;
		batchActiveLine: number | null;
		batchObservedLine: number | null;
		batchRunningLineText: string;
		batchSketchText: string | null;
		batchSketchGrainLabel: string;
		batchActiveDdlHighlighted: string;
		batchTotal: number;
		batchCurrent: number;
		batchRetryRound: number;
		batchActiveTokensIn: number | null;
		batchActiveTokensOut: number | null;
		batchTokensInTotal: number;
		batchTokensOutTotal: number;
		liveMs: number;
		batchFailureReport: BatchFailureReport | null;
		canSubmit: boolean;
		generationDisabled: boolean;
		error: string | null;
		batchPromptHistory: string[];
		canResumeBatch: boolean;
		batchResumeInfo: { nextLine: number | null; pending: number | null; total: number } | null;
		batchResuming: boolean;
		batchInterrupted: boolean;
		batchSuccess: number;
		onResumeBatch: () => void;
		stageLabel: string;
		canvasAspectId: CanvasAspectId;
		canvasAspectOptions: CanvasAspectOption[];
		canvasAspectMenuOpen: boolean;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		/** Sketch from life (Stage 0.5). Chosen per draw, not stored as a user setting. */
		sketchMode: SketchMode;
		onSelectSketchMode: (mode: SketchMode) => void;
		nextStage1Model: string;
		nextStage2Model: string;
		nextCatalogName: string;
		onToggleCanvasAspectMenu: () => void;
		onSelectCanvasAspect: (id: CanvasAspectId) => void | Promise<void>;
		onOpenModelSelection: () => void;
		onOpenCatalogModal: () => void;
		onClearInput: () => void;
		onRememberBatchPrompt: (prompt: string) => void | Promise<void>;
		onSubmit: () => void | Promise<void>;
		onForkDescription: () => void | Promise<void>;
		onStop: () => void;
	};

	let {
		inputMode = $bindable('single'),
		input = $bindable(''),
		batchInput = $bindable(''),
		lineNumbersText,
		batchNonEmpty,
		batchRunning,
		singleRunning,
		descriptionLocked,
		hideRunStatus = false,
		runTokensIn,
		runTokensOut,
		runAttempt = null,
		singleDdlReady,
		batchActiveLine,
		batchObservedLine,
		batchRunningLineText,
		batchSketchText,
		batchSketchGrainLabel,
		batchActiveDdlHighlighted,
		batchTotal,
		batchCurrent,
		batchRetryRound,
		batchActiveTokensIn,
		batchActiveTokensOut,
		batchTokensInTotal,
		batchTokensOutTotal,
		liveMs,
		batchFailureReport,
		canSubmit,
		generationDisabled,
		error,
		batchPromptHistory,
		canResumeBatch,
		batchResumeInfo,
		batchResuming,
		batchInterrupted,
		batchSuccess,
		onResumeBatch,
		stageLabel,
		canvasAspectId,
		canvasAspectOptions,
		canvasAspectMenuOpen,
		stage1ModelLabel,
		stage2ModelLabel,
		sketchMode,
		onSelectSketchMode,
		nextStage1Model,
		nextStage2Model,
		nextCatalogName,
		onToggleCanvasAspectMenu,
		onSelectCanvasAspect,
		onOpenModelSelection,
		onOpenCatalogModal,
		onClearInput,
		onRememberBatchPrompt,
		onSubmit,
		onForkDescription,
		onStop,
	}: Props = $props();

	const isJapanese = $derived(t().code === 'ja');

	// Progress sits on the tab only while the batch is running, so the tab returns
	// to its plain label the moment the run stops. batchCurrent is 0 outside a run.
	// During a retry round the counter runs over that round's own lines, marked
	// with ↻n so the numbers restarting does not read as the batch restarting.
	const batchRetryMark = $derived(batchRetryRound > 0 ? ` ↻${batchRetryRound}` : '');
	const batchProgress = $derived(
		batchRunning && batchTotal > 0 && batchCurrent > 0
			? `(${batchCurrent}/${batchTotal}${batchRetryMark})`
			: '',
	);
	// The counter is reserved at its widest form -- "(NN/NN)" for a two-digit total --
	// so the label beside it does not shuffle as the count crosses a digit boundary.
	// The tabs themselves are flex: 1 with a zero basis, so no tab can push another.
	const batchProgressWidth = $derived(
		2 * String(batchTotal).length + 3 + (batchRetryRound > 0 ? 2 + String(batchRetryRound).length : 0),
	);

	const tabItems = $derived([
		{ mode: 'single' as const, label: t().modeSingle, running: singleRunning, progress: '' },
		{ mode: 'batch' as const, label: t().modeBatch, running: batchRunning, progress: batchProgress },
	]);

	const singleInputStats = $derived.by(() => {
		// The guide is about the description, so the meter counts what the
		// drawing will read: the author's numbering and comments are not it.
		const source = pipelineDescription(input).trim();
		const asciiMostly = source.length > 0 && /^[\x00-\x7F\s.,;:!?()"-]+$/.test(source);
		const hasJapanese = /[\u3040-\u30ff\u3400-\u9fff]/.test(source);
		const useWords = !hasJapanese && (asciiMostly || (!source && t().code === 'en'));
		const guide = useWords ? 12 : 31;
		const count = useWords
			? (source.match(/[A-Za-z0-9]+(?:[-][A-Za-z0-9]+)*/g) ?? []).length
			: Array.from(source.replace(/\s/g, "")).length;
		return { count, guide, over: count > guide, useWords };
	});
</script>

<div class="panel-tabs">
	{#each tabItems as item (item.mode)}
		<Tooltip
			placement={item.mode === 'single' ? 'bottom-right' : 'bottom-left'}
			text={item.mode === 'single' ? t().tooltipInputTabSingle : t().tooltipInputTabBatch}
		>
			<button
				class="panel-tab"
				class:active={inputMode === item.mode}
				class:running={item.running}
				aria-busy={item.running}
				onclick={() => (inputMode = item.mode)}
			>
				<span class="tab-label">{item.label}</span>
				{#if item.progress}<span class="tab-progress" style="min-width: {batchProgressWidth}ch">{item.progress}</span>{/if}
				{#if item.running}<span class="tab-running-dot" aria-hidden="true"></span>{/if}
			</button>
		</Tooltip>
	{/each}
</div>

<section class="panel-section">
	<!-- The description is written before its conditions, immediately before painting. -->
	{#snippet inputConditionRows()}
		<div class="condition-rows" aria-label={t().nextWorkConditions}>
			<div class="condition-row">
				<div class="condition-row-head">
					<span class="condition-label">{t().modelButton}</span>
					<Tooltip text={t().tooltipInputModel}>
						<button class="ghost-btn condition-change" aria-label={t().tooltipInputModel} onclick={onOpenModelSelection}>{t().editButton}</button>
					</Tooltip>
				</div>
				<div class="condition-value condition-model-value">
					{#if nextStage1Model === nextStage2Model}
						<span title={nextStage1Model}>{nextStage1Model}</span>
					{:else}
						<span><small>{isJapanese ? '解釈' : 'Interpretation'}</small><span title={nextStage1Model}>{nextStage1Model}</span></span>
						<span><small>{isJapanese ? '描画' : 'Performance'}</small><span title={nextStage2Model}>{nextStage2Model}</span></span>
					{/if}
				</div>
			</div>
			<div class="condition-row">
				<div class="condition-row-head">
					<span class="condition-label">{t().colorCatalogButton}</span>
					<Tooltip text={t().tooltipInputCatalog}>
						<button class="ghost-btn condition-change" aria-label={t().tooltipInputCatalog} onclick={onOpenCatalogModal}>{t().editButton}</button>
					</Tooltip>
				</div>
				<!-- This still names the description-selected catalog when applicable. -->
				<span class="condition-value" title={nextCatalogName}>{nextCatalogName}</span>
			</div>
			<div class="condition-compact-rows">
				<div class="condition-compact-row">
					<Tooltip text={t().tooltipInputSketch}><SketchSelect value={sketchMode} {isJapanese} showValue onSelect={onSelectSketchMode} /></Tooltip>
				</div>
				<div class="condition-compact-row">
					<Tooltip text={t().tooltipInputWild}>
						<button
							type="button"
							class="ghost-btn wild-btn"
							class:active={wildSettings.enabled}
							aria-pressed={wildSettings.enabled}
							onclick={() => wildSettings.set(!wildSettings.enabled)}
						>{t().wildButton} {wildSettings.enabled ? t().wildEnabled : t().wildDisabled}</button>
					</Tooltip>
				</div>
				<div class="condition-compact-row">
					<Tooltip text={t().tooltipInputCanvas}>
						<CanvasAspectPlugin
							selected={canvasAspectId}
							options={canvasAspectOptions}
							open={canvasAspectMenuOpen}
							showValue
							onToggle={onToggleCanvasAspectMenu}
							onSelect={onSelectCanvasAspect}
					/>
					</Tooltip>
				</div>
				{#if inputMode === 'batch'}
					<div class="condition-compact-row">
						<Tooltip text={t().tooltipInputClear}>
							<button class="ghost-btn" onclick={onClearInput}>{t().clearInputBtn}</button>
						</Tooltip>
					</div>
				{/if}
			</div>
		</div>
	{/snippet}
	{#snippet inputSettings()}
		<h3 class="conditions-heading">{t().nextWorkConditions}</h3>
		{@render inputConditionRows()}
	{/snippet}

	{#if inputMode === 'single'}
		<div class="input-label">
			<div class="input-label-text">
				<div class="input-heading">{t().inputSectionLabel}</div>
				<div class="input-description">{t().inputSectionHint}</div>
			</div>
			<Tooltip placement="left" text={t().tooltipInputClear}>
				<button class="ghost-btn" onclick={onClearInput}>{t().clearInputBtn}</button>
			</Tooltip>
		</div>
		<!-- The grey ranges are painted behind the textarea, which cannot colour
		     its own text. -->
		<div class="input-ta-wrap">
			<LabelHighlight text={input} />
			<textarea
				bind:value={input}
				readonly={descriptionLocked}
				rows="5"
				spellcheck="false"
				placeholder={t().inputPlaceholder}
				class="input-ta"
			></textarea>
		</div>
		{#if descriptionLocked}
			<div class="description-lock">
				<span>{t().pipelineDescriptionLocked}</span>
				<button type="button" class="ghost-btn" disabled={singleRunning} onclick={onForkDescription}>{t().pipelineForkDescription}</button>
			</div>
		{/if}
		<div class="input-meta-row">
			<span class="input-comment-hint">{t().inputCommentHint}</span>
			<div class="input-meter" class:soft-over={singleInputStats.over} aria-hidden="true">{singleInputStats.useWords ? t().inputMeterWords(singleInputStats.count, singleInputStats.guide) : t().inputMeterChars(singleInputStats.count, singleInputStats.guide)}</div>
		</div>

		{@render inputSettings()}

		{#if singleRunning && !hideRunStatus}
			<div class="gen-status-wrap">
			<RunStatus
				label={stageLabel || t().stageDdlGenerating}
				stage1Model={stage1ModelLabel}
				stage2Model={stage2ModelLabel}
				elapsedMs={liveMs}
				tokensIn={runTokensIn}
				tokensOut={runTokensOut}
				attempt={runAttempt}
				onStop={onStop}
			/>
			</div>
		{:else}
			<Tooltip placement="top" text={t().tooltipSubmit}>
				<PaintButton onclick={onSubmit} disabled={!canSubmit || generationDisabled}>{t().submitBtn}</PaintButton>
			</Tooltip>
		{/if}

		{#if error}<p class="error-text">{error}</p>{/if}
	{:else if inputMode === 'batch'}
		<BatchPanel
			settings={inputConditionRows}
			{runTokensIn}
			{runTokensOut}
			{runAttempt}
			bind:batchInput
			{lineNumbersText}
			{batchNonEmpty}
			{batchRunning}
			{batchActiveLine}
			{batchObservedLine}
			{batchRunningLineText}
			{batchSketchText}
			{batchSketchGrainLabel}
			{batchActiveDdlHighlighted}
			{batchTotal}
			{batchCurrent}
			{batchRetryRound}
			{batchActiveTokensIn}
			{batchActiveTokensOut}
			{batchTokensInTotal}
			{batchTokensOutTotal}
			{liveMs}
			{batchFailureReport}
			{canSubmit}
			actionDisabled={singleRunning || generationDisabled}
			{error}
			{batchPromptHistory}
			{canResumeBatch}
			{batchResumeInfo}
			{batchResuming}
			{batchInterrupted}
			{batchSuccess}
			{onResumeBatch}
			{stage1ModelLabel}
			{stage2ModelLabel}
			{onRememberBatchPrompt}
			onSubmit={onSubmit}
			onStop={onStop}
		/>
	{/if}
</section>

<style>
	.panel-tabs { display: flex; border-bottom: 1px solid var(--border); }
	.panel-tabs :global(.tooltip-wrap) { flex: 1; }
	.panel-section > :global(.tooltip-wrap) { width: 100%; }
	.panel-tab {
		position: relative;
		flex: 1; padding: 10px; background: none; border: none;
		color: var(--fg3); font-size: var(--ui-font-size-12); cursor: pointer;
		font-family: inherit; border-bottom: 2px solid transparent;
		display: flex; align-items: center; justify-content: center; gap: 6px;
		min-height: 38px;
	}
	.panel-tab.active { color: var(--fg); border-bottom-color: var(--accent); }
	.panel-tab.running {
		color: var(--fg);
		background: color-mix(in srgb, var(--accent) 8%, transparent);
	}
	.panel-tab.running::before {
		content: "";
		position: absolute;
		left: 12px;
		right: 12px;
		bottom: -2px;
		height: 2px;
		background: linear-gradient(90deg, transparent, var(--accent), transparent);
		background-size: 180% 100%;
		animation: tabrun 1.1s linear infinite;
	}
	.panel-tab.active.running::before { background: var(--accent); animation: none; }
	/* Neither half of a running tab may break across lines. */
	.tab-label { line-height: 1; white-space: nowrap; }
	.tab-progress {
		line-height: 1;
		font-size: var(--ui-font-size-11);
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		text-align: center;
		/* The retry form carries a space, which is a break opportunity. */
		white-space: nowrap;
	}
	.tab-running-dot {
		width: 6px;
		height: 6px;
		border-radius: 50%;
		background: var(--accent);
		box-shadow: 0 0 0 3px color-mix(in srgb, var(--accent) 18%, transparent);
		animation: inkupulse 1s ease-in-out infinite;
	}
	.panel-section { display: flex; flex-direction: column; gap: 6px; }
	.conditions-heading { margin: 8px 0 2px; font-size: var(--ui-font-size-12); font-weight: 500; color: var(--fg2); }
	.condition-rows {
		display: grid;
		gap: 6px;
		min-width: 0;
	}
	.condition-row {
		display: grid;
		gap: 5px;
		min-width: 0;
		padding: 7px 0;
	}
	.condition-row + .condition-row { border-top: 1px solid var(--border); }
	.condition-row-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; }
	.condition-label {
		color: var(--fg2);
		font-size: var(--ui-font-size-12);
		line-height: 1.35;
		font-weight: 500;
	}
	.condition-value {
		min-width: 0;
		color: var(--fg);
		font-size: var(--ui-font-size-14);
		line-height: 1.35;
		overflow-wrap: anywhere;
	}
	.condition-model-value {
		display: grid;
		gap: 3px;
	}
	.condition-model-value > span {
		display: flex;
		gap: 6px;
		min-width: 0;
	}
	.condition-model-value > span > span { min-width: 0; overflow-wrap: anywhere; }
	.condition-model-value small {
		flex: none;
		color: var(--fg3);
		font-size: var(--ui-font-size-12);
		font-weight: 400;
	}
	.condition-change { white-space: nowrap; }
	.condition-compact-rows {
		position: relative;
		display: flex;
		flex-wrap: wrap;
		gap: 6px;
		padding-top: 6px;
		border-top: 1px solid var(--border);
	}
	.condition-compact-row {
		display: flex;
		align-items: center;
		min-width: 0;
	}
	.condition-compact-row :global(.tooltip-wrap) { flex: none; max-width: 100%; position: static; }
	/* Anchor menus to the whole conditions row so a wrapped trigger never
	   pushes its menu outside the narrow input panel. */
	.condition-compact-row :global(.sketch-plugin),
	.condition-compact-row :global(.canvas-aspect-plugin) { position: static; max-width: 100%; }
	.condition-compact-row :global(.sketch-menu),
	.condition-compact-row :global(.aspect-menu) { width: min(310px, 100%); }
	.condition-compact-row :global(.ghost-btn) { white-space: normal; text-align: left; }
	.input-label {
		display: flex;
		align-items: flex-start;
		justify-content: space-between;
		gap: 8px;
	}
	.input-label-text { min-width: 0; }
	.input-label :global(.tooltip-wrap) { flex: none; }
	.input-heading { color: var(--fg); font-size: var(--ui-font-size-14); line-height: 1.35; font-weight: 600; }
	.input-description { margin-top: 1px; color: var(--fg2); font-size: var(--ui-font-size-12); line-height: 1.45; }
	.wild-btn.active { background: var(--accent); color: var(--accent-fg); border-color: var(--accent); }
	.wild-btn.active:hover { background: var(--accent); }
	.input-ta-wrap {
		position: relative;
		display: flex;
		/* The mirror is inset to this box, so the box has to be the textarea's. */
		background: var(--panel);
		border-radius: var(--r);
	}
	.input-ta {
		width: 100%; padding: 9px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: transparent; color: var(--fg);
		position: relative;
		z-index: 1;
		font-family: inherit; font-size: var(--ui-font-size-14); line-height: 1.65;
		resize: vertical; outline: none;
	}
	.input-ta:focus { border-color: var(--accent); }
	.input-ta[readonly] { background: var(--bg2); color: var(--fg2); }
	.description-lock { display: flex; flex-wrap: wrap; align-items: center; justify-content: space-between; gap: 8px; font-size: var(--ui-font-size-12); color: var(--fg2); }
	.input-meta-row {
		display: flex;
		flex-wrap: wrap;
		align-items: flex-start;
		justify-content: space-between;
		gap: 2px 12px;
		margin-top: -3px;
	}
	.input-comment-hint {
		font-size: var(--ui-font-size-12);
		line-height: 1.5;
		color: var(--fg3);
	}
	.input-meter {
		min-width: 54px;
		margin-left: auto;
		font-size: var(--ui-font-size-12);
		line-height: 1.5;
		font-variant-numeric: tabular-nums;
		text-align: right;
		color: var(--fg3);
	}
	.input-meter.soft-over { color: color-mix(in srgb, var(--fg) 78%, transparent); }
	.gen-status-wrap { margin-top: 4px; }
	.error-text { color: var(--danger); font-size: var(--ui-font-size-12); white-space: pre-line; }
	@media (max-width: 430px) {
		.condition-compact-row { max-width: 100%; }
	}
	@keyframes inkupulse {
		0%, 100% { opacity: 1; transform: scale(1); }
		50% { opacity: 0.4; transform: scale(0.7); }
	}
	@keyframes tabrun {
		from { background-position: 180% 0; }
		to { background-position: -180% 0; }
	}
</style>
