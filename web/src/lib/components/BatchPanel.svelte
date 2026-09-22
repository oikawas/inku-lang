<script lang="ts">
	import type { Snippet } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
	import LabelHighlight from './LabelHighlight.svelte';
	import PaintButton from './PaintButton.svelte';
	import RunStatus from './RunStatus.svelte';

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
		batchInput: string;
		lineNumbersText: string;
		batchNonEmpty: number;
		batchRunning: boolean;
		batchActiveLine: number | null;
		batchObservedLine: number | null;
		batchRunningLineText: string;
		batchSketchText: string | null;
		batchSketchGrainLabel: string;
		batchActiveDdlHighlighted: string;
		batchTotal: number;
		batchCurrent: number;
		batchRetryRound: number;
		runTokensIn: number | null;
		runTokensOut: number | null;
		batchActiveTokensIn: number | null;
		batchActiveTokensOut: number | null;
		batchTokensInTotal: number;
		batchTokensOutTotal: number;
		liveMs: number;
		batchFailureReport: BatchFailureReport | null;
		canSubmit: boolean;
		actionDisabled: boolean;
		error: string | null;
		batchPromptHistory: string[];
		/** Set when the last run stopped before the end of its prompt. */
		canResumeBatch: boolean;
		/** The stopped batch's remaining work, found without changing the editor. */
		batchResumeInfo?: { nextLine: number | null; pending: number | null; total: number } | null;
		/** A resume scan is in progress; its result has not yet replaced the editor. */
		batchResuming?: boolean;
		/** The last batch was explicitly stopped before it reached its end. */
		batchInterrupted?: boolean;
		/** Completed works from the most recent batch, including a stopped one. */
		batchSuccess?: number;
		onResumeBatch: () => void;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		onRememberBatchPrompt: (prompt: string) => void | Promise<void>;
		onSubmit: () => void | Promise<void>;
		onStop: () => void;
		// The shared button row and settings readout, rendered by the parent but
		// placed here so it sits between the input box and the batch options.
		settings?: Snippet;
	};

	let {
		batchInput = $bindable(''),
		lineNumbersText,
		batchNonEmpty,
		batchRunning,
		batchActiveLine,
		batchObservedLine,
		batchRunningLineText,
		batchSketchText,
		batchSketchGrainLabel,
		batchActiveDdlHighlighted,
		batchTotal,
		batchCurrent,
		batchRetryRound,
		runTokensIn,
		runTokensOut,
		batchActiveTokensIn,
		batchActiveTokensOut,
		batchTokensInTotal,
		batchTokensOutTotal,
		liveMs,
		batchFailureReport,
		canSubmit,
		actionDisabled,
		error,
		batchPromptHistory,
		canResumeBatch,
		batchResumeInfo = null,
		batchResuming = false,
		batchInterrupted = false,
		batchSuccess = 0,
		onResumeBatch,
		stage1ModelLabel,
		stage2ModelLabel,
		onRememberBatchPrompt,
		onSubmit,
		onStop,
		settings,
	}: Props = $props();

	let batchTextareaEl = $state<HTMLTextAreaElement | null>(null);
	let batchScrollTop = $state(0);
	let batchScrollLeft = $state(0);
	let selectedHistoryPrompt = $state('');
	let historyMenuOpen = $state(false);
	let historyMenuWrapEl = $state<HTMLDivElement | null>(null);
	const displayLineNumbersText = $derived(batchInput.trim() ? lineNumbersText : t().batchPlaceholder.split('\n').map((_, i) => String(i + 1)).join('\n'));
	function normalizePrompt(text: string): string {
		return text.trim().replace(/\r\n/g, '\n');
	}

	function rememberCurrentPrompt() {
		const prompt = normalizePrompt(batchInput);
		if (!prompt) return;
		void onRememberBatchPrompt(prompt);
	}

	function restoreHistoryPrompt(prompt: string) {
		historyMenuOpen = false;
		if (!prompt || batchRunning || batchResuming) return;
		selectedHistoryPrompt = prompt;
		batchInput = prompt;
	}

	/** What a stored batch is called in the picker: its first line. */
	function historyPromptLabel(prompt: string): string {
		return prompt.split('\n')[0];
	}

	function closeHistoryMenuOnOutsideClick(event: MouseEvent) {
		if (!historyMenuOpen) return;
		if (historyMenuWrapEl?.contains(event.target as Node)) return;
		historyMenuOpen = false;
	}

	function submitAndRemember() {
		rememberCurrentPrompt();
		if (!batchResuming) void onSubmit();
	}

	function tokenPair(input: number | null, output: number | null): string {
		return `${input ?? '-'}→${output ?? '-'}tok`;
	}
</script>

<svelte:window
	onclick={closeHistoryMenuOnOutsideClick}
	onkeydown={(event) => { if (event.key === 'Escape') historyMenuOpen = false; }}
/>

<div class="batch-label">
	<span class="batch-label-text"><strong>{t().batchSectionLabel}</strong><span class="batch-label-hint">{t().batchSectionHint}</span></span>
	{#if batchInterrupted && !batchRunning}
		<span class="batch-interrupted-mark">{t().batchInterruptedLabel}</span>
	{/if}
</div>
{#if batchRunning}
	<!-- The box is read-only for the length of the run, so the whole list is not
	     worth its height: the one line being painted is what the author is
	     watching. Its number is kept -- it is how the failure report, the
	     history label and the observer below all name this work. -->
	<div class="batch-current">
		<span class="batch-current-num">{batchActiveLine ?? '-'}</span>
		<span class="batch-current-text">{batchRunningLineText}</span>
	</div>
{:else}
	<div class="batch-wrap">
		<div class="line-nums" aria-hidden="true">
			<!-- The gutter is a plain block, so it is scrolled by hand to stay level
			     with the textarea it labels. -->
			<div class="line-nums-inner" style={`transform: translateY(${-batchScrollTop}px)`}>{displayLineNumbersText}</div>
		</div>
		<div class="batch-ta-wrap">
			<LabelHighlight text={batchInput} wrap={false} scrollTop={batchScrollTop} scrollLeft={batchScrollLeft} />
			<textarea
				class="batch-ta"
				bind:this={batchTextareaEl}
				bind:value={batchInput}
				disabled={batchResuming}
				rows="5"
				spellcheck="false"
				wrap="off"
				placeholder={t().batchPlaceholder}
				onscroll={() => {
					batchScrollTop = batchTextareaEl?.scrollTop ?? 0;
					batchScrollLeft = batchTextareaEl?.scrollLeft ?? 0;
				}}
			></textarea>
		</div>
	</div>
{/if}
{#if batchNonEmpty > 0 && !batchRunning}<p class="batch-info">{t().batchCount(batchNonEmpty)}</p>{/if}

<!-- Restoring a past batch refills the input box, so the picker sits directly
     under it rather than down with the run options.

     A list of our own, not a native dropdown: how tall the browser opens one is
     the browser's to decide, and fifty stored batches want a list bounded to
     half the window with a bar to scroll it. Same shape as the aspect menu. -->
{#if !batchRunning && batchPromptHistory.length > 0}
	<div class="batch-history" bind:this={historyMenuWrapEl}>
		<button
			type="button"
			class="batch-history-trigger"
			aria-haspopup="listbox"
			aria-expanded={historyMenuOpen}
			aria-label={t().batchHistoryLabel}
			onclick={() => (historyMenuOpen = !historyMenuOpen)}
			disabled={batchResuming}
		>
			<span class="batch-history-current">
				{selectedHistoryPrompt ? historyPromptLabel(selectedHistoryPrompt) : t().batchHistoryPlaceholder}
			</span>
			<span class="batch-history-caret" aria-hidden="true">▾</span>
		</button>
		{#if historyMenuOpen}
			<div class="batch-history-menu" role="listbox" aria-label={t().batchHistoryLabel}>
				{#each batchPromptHistory as prompt, i (`${i}-${prompt}`)}
					<button
						type="button"
						role="option"
						aria-selected={prompt === selectedHistoryPrompt}
						class:selected={prompt === selectedHistoryPrompt}
						disabled={batchResuming}
						onclick={() => restoreHistoryPrompt(prompt)}
					>{historyPromptLabel(prompt)}</button>
				{/each}
			</div>
		{/if}
	</div>
{/if}

{#if !batchRunning && canResumeBatch}
	<section class="batch-resume-card" aria-label={t().batchResumeTitle}>
		<div class="batch-resume-copy">
			<strong>{t().batchResumeTitle}</strong>
			<p>
				{#if batchResumeInfo?.nextLine !== null && batchResumeInfo?.nextLine !== undefined && batchResumeInfo?.pending !== null && batchResumeInfo?.pending !== undefined}
					{t().batchResumeKnown(batchResumeInfo.nextLine, batchResumeInfo.pending, batchResumeInfo.total)}
				{:else}
					{t().batchResumeUnknown(batchResumeInfo?.total ?? 0)}
				{/if}
			</p>
			{#if batchResumeInfo?.pending !== null && batchResumeInfo?.pending !== undefined}
				<span>{t().batchResumeCompleted(batchResumeInfo.total - batchResumeInfo.pending)}</span>
			{/if}
			<span>{t().batchResumeRestores}</span>
		</div>
		<button type="button" class="ghost-btn batch-resume-btn" onclick={onResumeBatch} disabled={actionDisabled || batchResuming}>
			{batchResuming ? t().batchResumeScanning : t().batchResumeBtn}
		</button>
	</section>
{/if}

<section class="batch-next-conditions" aria-label={t().batchNextConditionsLabel} aria-busy={batchResuming}>
	<div class="batch-next-conditions-head">
		<span>{t().batchNextConditionsLabel}</span>
		{#if batchResuming}<span>{t().batchResumeScanning}</span>{/if}
	</div>
	<div class:batch-controls-busy={batchResuming} inert={batchResuming}>
		{@render settings?.()}
	</div>
</section>


{#if batchRunning && batchTotal > 0}
	<div class="batch-progress-wrap">
		<RunStatus
			label={batchRetryRound > 0
				? t().batchRetryProgress(batchCurrent, batchTotal, batchRetryRound)
				: t().batchProgress(batchCurrent, batchTotal)}
			stage1Model={stage1ModelLabel}
			stage2Model={stage2ModelLabel}
			elapsedMs={liveMs}
			tokensIn={batchTokensInTotal || runTokensIn}
			tokensOut={batchTokensOutTotal || runTokensOut}
			onStop={onStop}
		/>
	</div>
{:else}
	<div class="batch-actions" class:batch-actions-busy={batchResuming}>
		<span class="batch-action-label">{t().batchNewRunLabel}</span>
		<PaintButton onclick={submitAndRemember} disabled={!canSubmit || actionDisabled || batchResuming}>{t().batchNewRunBtn}</PaintButton>
	</div>
{/if}

{#if error}<p class="error-text">{error}</p>{/if}
<!-- Sketch from life (Stage 0.5), read-only here. Above the instructions because it comes
     before them, the same order the describe tab keeps. Written when a line
     returns, so it is the prose of the work the observer below is showing. -->
{#if batchRunning && batchSketchText !== null}
	<div class="batch-observe batch-sketch">
		<div class="batch-observe-head">
			<span>{t().sketchLabel}</span>
			<div class="batch-observe-meta">
				{#if batchObservedLine !== null}<span>{t().batchActiveLine(batchObservedLine)}</span>{/if}
				<span>{t().sketchGrainLabel}: {batchSketchGrainLabel}</span>
			</div>
		</div>
		<div class="batch-observe-body batch-sketch-body">{batchSketchText}</div>
	</div>
{/if}
{#if batchRunning}
	<div class="batch-observe">
		<div class="batch-observe-head">
			<span>{t().batchActiveDdlLabel}</span>
			<div class="batch-observe-meta">
				<!-- The line the instructions below came from, not the one being
				     painted: the two differ for the length of every line. -->
				{#if batchObservedLine !== null}<span>{t().batchActiveLine(batchObservedLine)}</span>{/if}
				<span><span class="batch-metric-label">{t().statsTokens}</span>{tokenPair(batchActiveTokensIn, batchActiveTokensOut)}</span>
			</div>
		</div>
		<div class="batch-observe-body">{@html batchActiveDdlHighlighted}</div>
	</div>
{/if}
{#if batchFailureReport && !batchRunning}
	<div class="batch-summary has-failures">
		<div class="batch-summary-line">{t().batchSummary(batchFailureReport.success, batchFailureReport.failures.length, batchFailureReport.total)}</div>
		<div class="batch-failure-title">{t().batchFailureTitle}</div>
		<ul class="batch-failure-list">
			{#each batchFailureReport.failures as failure (failure.line)}
				<li>
					<span class="batch-failure-line">{t().batchFailureLine(failure.line)}</span>
					<span class="batch-failure-input">{failure.input}</span>
					<span class="batch-failure-message">{failure.message}</span>
				</li>
			{/each}
		</ul>
	</div>
{/if}

<style>
	/* Same shape as the label over the description box in InputPanel. */
	.batch-label {
		display: flex;
		align-items: baseline;
		justify-content: space-between;
		gap: 8px;
		font-size: 14px;
		line-height: 1.5;
		color: var(--fg2);
		font-weight: 400;
	}
	.batch-label-text { display: flex; min-width: 0; gap: 2px; }
	.batch-label strong { font-weight: 600; color: var(--fg); }
	.batch-label-hint { color: var(--fg2); }
	.batch-interrupted-mark {
		flex: 0 0 auto;
		color: var(--danger);
		font-size: 12px;
		font-weight: 500;
	}
	.batch-wrap {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
		/* The box is sized here, not by the textarea: the gutter is a plain block
		   whose content is as tall as the line count, so leaving the height to the
		   children let a long batch stretch the box past the bottom of the panel.
		   Resizing moves the gutter and the text together. */
		height: clamp(140px, 22vh, 220px);
		resize: vertical;
		min-height: 120px;
	}
	.line-nums {
		flex: 0 0 auto;
		background: var(--bg2); border-right: 1px solid var(--border);
		padding: 9px 6px; font-size: 14px; line-height: 1.65;
		text-align: right; color: var(--fg3); user-select: none;
		font-family: inherit;
		white-space: pre; min-width: 2rem; font-variant-numeric: tabular-nums;
		overflow: hidden;
	}
	.batch-ta {
		width: 100%; padding: 9px 10px;
		box-sizing: border-box;
		border: none;
		border-radius: 0;
		background: transparent; color: var(--fg);
		font-family: inherit; font-size: 14px; line-height: 1.65;
		resize: none; outline: none;
		white-space: pre;
		overflow-wrap: normal;
		overflow: auto;
		position: relative;
		z-index: 1;
		/* Fills the box; the box itself carries the height and the resize grip. */
		height: 100%;
	}
	.batch-ta:focus { border-color: var(--accent); }
	/* The line being painted, in place of the box. The gutter's look is kept for
	   the number so the two read as the same column they were. */
	.batch-current {
		display: flex;
		align-items: baseline;
		gap: 8px;
		box-sizing: border-box;
		border: 1px solid var(--border);
		border-radius: 4px;
		background: var(--bg2);
		padding: 8px 10px;
		font-size: 14px;
		line-height: 1.65;
	}
	.batch-current-num {
		flex: 0 0 auto;
		min-width: 2rem;
		text-align: right;
		color: var(--fg3);
		font-variant-numeric: tabular-nums;
		user-select: none;
	}
	.batch-current-text {
		min-width: 0;
		color: var(--fg);
		word-break: break-word;
	}
	.batch-ta-wrap {
		position: relative;
		display: flex;
		flex: 1;
		min-width: 0;
		background: var(--panel);
		overflow: hidden;
	}
	.batch-info { margin: 5px 0 0; font-size: 12px; color: var(--fg3); }
	.batch-history {
		position: relative;
		display: flex;
		align-items: center;
		gap: 5px;
		flex-wrap: wrap;
	}
	.batch-history-trigger {
		flex: 1;
		min-width: min(220px, 100%);
		display: flex;
		align-items: center;
		gap: 6px;
		padding: 4px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-family: inherit;
		font-size: var(--btn-sm-font-size);
		text-align: left;
		cursor: pointer;
	}
	.batch-history-trigger:hover { background: var(--bg2); }
	.batch-history-trigger:disabled { cursor: wait; opacity: 0.65; }
	.batch-history-current {
		flex: 1;
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.batch-history-caret { flex: 0 0 auto; color: var(--fg3); }
	.batch-history-menu {
		position: absolute;
		top: calc(100% + 4px);
		left: 0;
		right: 0;
		z-index: 80;
		/* Half the window is the ceiling the author asked for; past it the list
		   scrolls rather than growing. */
		max-height: 50vh;
		overflow: auto;
		padding: 4px;
		border: 1px solid var(--border2);
		border-radius: var(--r-lg);
		background: var(--panel);
		box-shadow: 0 10px 32px rgba(0,0,0,0.18);
	}
	.batch-history-menu button {
		width: 100%;
		display: block;
		padding: 6px 8px;
		border: none;
		border-radius: var(--r);
		background: transparent;
		color: var(--fg);
		font-family: inherit;
		font-size: var(--btn-sm-font-size);
		text-align: left;
		white-space: nowrap;
		overflow: hidden;
		text-overflow: ellipsis;
		cursor: pointer;
	}
	.batch-history-menu button:hover { background: var(--bg2); }
	.batch-history-menu button.selected {
		background: var(--bg2);
		box-shadow: inset 3px 0 0 var(--fg2);
	}
	.batch-next-conditions {
		margin-top: 12px;
		padding-top: 10px;
		border-top: 1px solid var(--border);
	}
	.batch-next-conditions-head {
		display: flex;
		justify-content: space-between;
		gap: 8px;
		margin-bottom: 6px;
		color: var(--fg2);
		font-size: 12px;
		font-weight: 600;
	}
	.batch-next-conditions-head span:last-child { color: var(--fg3); font-weight: 400; }
	.batch-controls-busy { cursor: wait; opacity: 0.62; }
	.batch-resume-card {
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 12px;
		margin-top: 12px;
		padding: 10px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--bg2);
	}
	.batch-resume-copy { min-width: 0; color: var(--fg2); font-size: 12px; line-height: 1.5; }
	.batch-resume-copy strong { display: block; color: var(--fg); font-size: 14px; }
	.batch-resume-copy p { margin: 2px 0; }
	.batch-resume-copy span { display: block; color: var(--fg3); }
	.batch-resume-btn { flex: 0 0 auto; }
	.batch-actions {
		display: flex;
		align-items: stretch;
		gap: 6px;
		margin-top: 12px;
	}
	.batch-action-label {
		display: flex;
		align-items: center;
		color: var(--fg2);
		font-size: 12px;
		white-space: nowrap;
	}
	.batch-actions-busy {
		cursor: wait;
		opacity: 0.62;
	}
	.batch-actions :global(.paint-btn.block) {
		flex: 1;
		width: auto;
	}
	.batch-sketch-body {
		white-space: pre-wrap;
		word-break: break-word;
	}
	.batch-progress-wrap { margin-top: 8px; }
	.batch-metric-label {
		display: inline-block;
		min-width: 3.9em;
		margin-right: 5px;
		color: var(--fg3);
		font-variant-numeric: normal;
	}
	.error-text { color: var(--danger); font-size: 12px; white-space: pre-line; }
	.batch-summary {
		margin-top: 8px;
		padding: 8px 10px;
		border: 1px solid #b8c7ab;
		border-radius: var(--r);
		background: #f5f8f1;
		color: #40552b;
		font-size: 12px;
	}
	.batch-summary.has-failures {
		border-color: #d9b4ae;
		background: #fff6f4;
		color: #7c332b;
	}
	.batch-summary-line { font-weight: 500; }
	.batch-failure-title { margin-top: 6px; color: var(--fg2); font-size: 11px; }
	.batch-failure-list {
		margin: 4px 0 0;
		padding: 0;
		list-style: none;
		display: flex;
		flex-direction: column;
		gap: 4px;
	}
	.batch-failure-list li {
		display: grid;
		grid-template-columns: 48px minmax(0, 1fr);
		gap: 3px 8px;
	}
	.batch-failure-line { color: var(--fg2); font-variant-numeric: tabular-nums; }
	.batch-failure-input {
		min-width: 0;
		overflow: hidden;
		text-overflow: ellipsis;
		white-space: nowrap;
	}
	.batch-failure-message {
		grid-column: 2;
		color: var(--danger);
		font-size: 11px;
		word-break: break-word;
	}
	.batch-observe {
		margin-top: 8px;
		border: 1px solid #c8d1bd;
		border-radius: var(--r);
		background: #fbfcf8;
		overflow: hidden;
	}
	.batch-observe-head {
		display: grid;
		grid-template-columns: minmax(72px, 0.65fr) minmax(0, 1.35fr);
		gap: 8px;
		padding: 6px 9px;
		border-bottom: 1px solid #d9dfd1;
		color: #4a5b38;
		font-size: 11px;
		font-weight: 600;
	}
	.batch-observe-meta {
		display: grid;
		grid-template-columns: minmax(54px, auto) minmax(0, 1fr);
		gap: 6px 8px;
		color: var(--fg3);
		font-weight: 400;
		font-variant-numeric: tabular-nums;
		min-width: 0;
		justify-self: stretch;
	}
	.batch-observe-meta span {
		color: var(--fg3);
		font-weight: 400;
		font-variant-numeric: tabular-nums;
		min-width: 0;
		white-space: nowrap;
	}
	/* The batch panel's status blocks were authored in light-theme paper colours
	   only, so on the dark theme they read as white sheets over the panel. */
	:global(html[data-theme='dark']) .batch-observe {
		border-color: var(--border2);
		background: var(--panel);
	}
	:global(html[data-theme='dark']) .batch-observe-head {
		border-bottom-color: var(--border);
		color: var(--fg2);
	}
	:global(html[data-theme='dark']) .batch-summary {
		border-color: rgba(154, 183, 220, 0.35);
		background: color-mix(in srgb, var(--accent) 12%, var(--panel));
		color: var(--fg);
	}
	:global(html[data-theme='dark']) .batch-summary.has-failures {
		border-color: rgba(255, 154, 134, 0.45);
		background: color-mix(in srgb, var(--danger) 12%, var(--panel));
		color: var(--fg);
	}
	.batch-observe-body {
		margin: 0;
		padding: 9px 10px;
		max-height: 132px;
		overflow: auto;
		color: var(--fg2);
		font-family: inherit;
		font-size: 12px;
		line-height: 1.55;
		white-space: pre-wrap;
	}
	@media (max-width: 600px) {
		.batch-label { align-items: flex-start; }
		.batch-wrap { height: clamp(140px, 26vh, 220px); }
		.batch-resume-card { align-items: stretch; flex-direction: column; gap: 8px; }
		.batch-resume-btn { width: 100%; }
		.batch-actions { align-items: stretch; flex-direction: column; }
		.batch-action-label { min-height: 0; }
		.batch-actions :global(.paint-btn.block) { width: 100%; }
		.batch-observe-head { grid-template-columns: 1fr; gap: 3px; }
		.batch-observe-meta { justify-self: start; }
		.batch-failure-list li { grid-template-columns: 44px minmax(0, 1fr); }
	}
</style>
