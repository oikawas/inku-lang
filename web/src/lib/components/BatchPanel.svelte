<script lang="ts">
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
		randomColorCatalog: boolean;
		showCrab: boolean;
		stage1ModelLabel: string;
		stage2ModelLabel: string;
		onOpenModelSelection: () => void;
		onRememberBatchPrompt: (prompt: string) => void | Promise<void>;
		onSubmit: () => void | Promise<void>;
		onStop: () => void;
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
		randomColorCatalog = $bindable(false),
		showCrab,
		stage1ModelLabel,
		stage2ModelLabel,
		onOpenModelSelection,
		onRememberBatchPrompt,
		onSubmit,
		onStop,
	}: Props = $props();

	let batchTextareaEl = $state<HTMLTextAreaElement | null>(null);
	let batchScrollTop = $state(0);
	let selectedHistoryPrompt = $state('');
	const displayLineNumbersText = $derived(batchInput.trim() ? lineNumbersText : t().batchPlaceholder.split('\n').map((_, i) => String(i + 1)).join('\n'));
	const batchTextareaHeight = $derived(`${Math.max(240, displayLineNumbersText.split('\n').length * 21.45 + 18)}px`);
	const batchActiveLineStyle = $derived(
		batchActiveLine === null
			? ''
			: `--batch-active-top: ${9 + (batchActiveLine - 1) * 21.45 - batchScrollTop}px`
	);

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

<div class="batch-model-summary">
	<span><b>Stage 1</b>{stage1ModelLabel}</span><span><b>Stage 2</b>{stage2ModelLabel}</span>
	<button type="button" disabled={batchRunning} onclick={onOpenModelSelection}>{t().modelSelectButton}</button>
</div>

<div class="batch-wrap">
	<div class="line-nums" aria-hidden="true">{displayLineNumbersText}</div>
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
			style={`height: ${batchTextareaHeight}`}
			onscroll={() => (batchScrollTop = batchTextareaEl?.scrollTop ?? 0)}
		></textarea>
	</div>
</div>
{#if batchNonEmpty > 0}<p class="batch-info">{t().batchCount(batchNonEmpty)}</p>{/if}
{#if !batchRunning}
	<div class="batch-tools">
		<label class="batch-option">
			<input type="checkbox" bind:checked={randomColorCatalog} />
			<span>{t().batchRandomColorCatalog}</span>
		</label>
		{#if batchPromptHistory.length > 0}
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
	</div>
{/if}

{#if batchRunning && batchTotal > 0}
	<div class="batch-progress-wrap">
		<RunStatus
			label={t().batchProgress(batchCurrent, batchTotal)}
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
	.batch-model-summary { display: grid; grid-template-columns: minmax(0,1fr) minmax(0,1fr) auto; align-items: stretch; gap: 6px; margin-bottom: 8px; }
	.batch-model-summary span { display: grid; gap: 2px; min-width: 0; padding: 7px 8px; border: 1px solid var(--border); border-radius: var(--r); background: var(--panel); color: var(--fg2); font-size: 10px; overflow-wrap: anywhere; }
	.batch-model-summary b { color: var(--fg3); font-size: 8px; letter-spacing: .06em; }
	.batch-model-summary button { padding: 6px 10px; border: 1px solid var(--border2); border-radius: var(--r); background: var(--panel); color: var(--accent); font: inherit; font-size: 10px; cursor: pointer; }
	.batch-model-summary button:disabled { opacity: .45; cursor: not-allowed; }
	.batch-wrap {
		display: flex;
		border: 1px solid var(--border2);
		border-radius: var(--r);
		overflow: hidden;
	}
	.line-nums {
		background: var(--bg2); border-right: 1px solid var(--border);
		padding: 9px 6px; font-size: 13px; line-height: 1.65;
		text-align: right; color: var(--fg3); user-select: none;
		font-family: inherit;
		white-space: pre; min-width: 2rem; font-variant-numeric: tabular-nums;
	}
	.batch-ta {
		width: 100%; padding: 9px 10px;
		box-sizing: border-box;
		border: none;
		border-radius: 0;
		background: transparent; color: var(--fg);
		font-family: inherit; font-size: 13px; line-height: 1.65;
		resize: vertical; outline: none;
		white-space: pre;
		overflow-wrap: normal;
		overflow-x: auto;
		position: relative;
		z-index: 1;
		min-height: 240px;
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
	.batch-tools {
		display: flex;
		flex-direction: column;
		gap: 6px;
		margin-top: 2px;
	}
	.batch-option {
		display: inline-flex;
		align-items: center;
		gap: 6px;
		color: var(--fg2);
		font-size: 11px;
	}
	.batch-option input { margin: 0; }
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
