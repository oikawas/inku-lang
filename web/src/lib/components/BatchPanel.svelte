<script lang="ts">
	import type { Snippet } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';
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
		stage1ModelLabel,
		stage2ModelLabel,
		onRememberBatchPrompt,
		onSubmit,
		onStop,
		settings,
	}: Props = $props();

	// Row pitch of the textarea (13px × 1.65). The gutter, the active-line band
	// and the follow-the-run scrolling all step by it.
	const LINE_HEIGHT = 21.45;
	const TEXT_PAD_TOP = 9;

	let batchTextareaEl = $state<HTMLTextAreaElement | null>(null);
	let batchScrollTop = $state(0);
	let selectedHistoryPrompt = $state('');
	const displayLineNumbersText = $derived(batchInput.trim() ? lineNumbersText : t().batchPlaceholder.split('\n').map((_, i) => String(i + 1)).join('\n'));
	const batchActiveLineStyle = $derived(
		batchActiveLine === null
			? ''
			: `--batch-active-top: ${TEXT_PAD_TOP + (batchActiveLine - 1) * LINE_HEIGHT - batchScrollTop}px`
	);

	// The box no longer grows with the line count, so on a long batch the line
	// being painted can sit below the fold. Keep it in view while the box is
	// read-only; once the run ends the caret is the user's again.
	$effect(() => {
		const line = batchActiveLine;
		const el = batchTextareaEl;
		if (!batchRunning || line === null || !el) return;
		const top = (line - 1) * LINE_HEIGHT;
		const viewTop = el.scrollTop;
		const viewBottom = viewTop + el.clientHeight - LINE_HEIGHT * 2;
		if (top < viewTop || top > viewBottom) {
			el.scrollTop = Math.max(0, top - el.clientHeight / 2);
		}
	});

	function normalizePrompt(text: string): string {
		return text.trim().replace(/\r\n/g, '\n');
	}

	function rememberCurrentPrompt() {
		const prompt = normalizePrompt(batchInput);
		if (!prompt) return;
		void onRememberBatchPrompt(prompt);
	}

	function restoreSelectedHistoryPrompt() {
		if (!selectedHistoryPrompt || batchRunning) return;
		batchInput = selectedHistoryPrompt;
	}

	function submitAndRemember() {
		rememberCurrentPrompt();
		void onSubmit();
	}

	function tokenPair(input: number | null, output: number | null): string {
		return `${input ?? '-'}→${output ?? '-'}tok`;
	}
</script>

<div class="batch-label">
	<span class="batch-label-text"><strong>{t().batchSectionLabel}</strong>{t().batchSectionHint}</span>
</div>
<div class="batch-wrap">
	<div class="line-nums" aria-hidden="true">
		<!-- The gutter is a plain block, so it is scrolled by hand to stay level
		     with the textarea it labels. -->
		<div class="line-nums-inner" style={`transform: translateY(${-batchScrollTop}px)`}>{displayLineNumbersText}</div>
	</div>
	<div class="batch-ta-wrap">
		{#if batchRunning && batchActiveLine !== null}
			<div class="batch-active-line" style={batchActiveLineStyle}></div>
		{/if}
		<textarea
			class="batch-ta"
			bind:this={batchTextareaEl}
			bind:value={batchInput}
			rows="5"
			spellcheck="false"
			wrap="off"
			placeholder={t().batchPlaceholder}
			readonly={batchRunning}
			onscroll={() => (batchScrollTop = batchTextareaEl?.scrollTop ?? 0)}
		></textarea>
	</div>
</div>
{#if batchNonEmpty > 0}<p class="batch-info">{t().batchCount(batchNonEmpty)}</p>{/if}

<!-- Restoring a past batch refills the input box, so the picker sits directly
     under it rather than down with the run options. -->
{#if !batchRunning && batchPromptHistory.length > 0}
	<div class="batch-history">
		<select
			bind:value={selectedHistoryPrompt}
			aria-label={t().batchHistoryLabel}
			onchange={restoreSelectedHistoryPrompt}
		>
			<option value="">{t().batchHistoryPlaceholder}</option>
			{#each batchPromptHistory as prompt, i (`${i}-${prompt}`)}
				<option value={prompt}>{prompt.split('\n')[0]}</option>
			{/each}
		</select>
	</div>
{/if}

{@render settings?.()}


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
	<PaintButton onclick={submitAndRemember} disabled={!canSubmit || actionDisabled}>{t().submitBtn}</PaintButton>
{/if}

{#if error}<p class="error-text">{error}</p>{/if}
{#if batchRunning}
	<div class="batch-observe">
		<div class="batch-observe-head">
			<span>{t().batchActiveDdlLabel}</span>
			<div class="batch-observe-meta">
				{#if batchActiveLine !== null}<span>{t().batchActiveLine(batchActiveLine)}</span>{/if}
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
		font-size: 12px;
		line-height: 1.5;
		color: var(--fg2);
		font-weight: 400;
	}
	.batch-label-text { min-width: 0; }
	.batch-label strong { font-weight: 600; color: var(--fg); }
	.batch-wrap {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
		/* The box is sized here, not by the textarea: the gutter is a plain block
		   whose content is as tall as the line count, so leaving the height to the
		   children let a long batch stretch the box past the bottom of the panel.
		   Resizing moves the gutter and the text together. */
		height: clamp(200px, 42vh, 640px);
		resize: vertical;
		min-height: 120px;
	}
	.line-nums {
		flex: 0 0 auto;
		background: var(--bg2); border-right: 1px solid var(--border);
		padding: 9px 6px; font-size: 13px; line-height: 1.65;
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
		font-family: inherit; font-size: 13px; line-height: 1.65;
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
	.batch-ta:read-only {
		color: var(--fg2);
		cursor: default;
	}
	.batch-ta-wrap {
		position: relative;
		display: flex;
		flex: 1;
		min-width: 0;
		background: var(--panel);
		overflow: hidden;
	}
	.batch-info { font-size: 11px; color: var(--fg3); }
	.batch-history {
		display: flex;
		align-items: center;
		gap: 5px;
		flex-wrap: wrap;
	}
	.batch-history select {
		flex: 1;
		min-width: min(220px, 100%);
		padding: 4px 7px;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		background: var(--panel);
		color: var(--fg2);
		font-family: inherit;
		font-size: 11px;
	}
	.batch-active-line {
		position: absolute;
		top: var(--batch-active-top, -100px);
		left: 0;
		right: 0;
		height: 21.45px;
		background: #fff0c2;
		border-top: 1px solid rgba(189, 143, 52, 0.25);
		border-bottom: 1px solid rgba(189, 143, 52, 0.25);
		pointer-events: none;
		z-index: 0;
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
	:global(html[data-theme='dark']) .batch-active-line {
		background: rgba(189, 143, 52, 0.26);
		border-top-color: rgba(226, 191, 130, 0.35);
		border-bottom-color: rgba(226, 191, 130, 0.35);
	}
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
</style>
