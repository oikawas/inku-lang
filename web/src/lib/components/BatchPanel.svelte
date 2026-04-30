<script lang="ts">
	import { onMount } from 'svelte';
	import { t } from '$lib/i18n/index.svelte';

	const BATCH_PROMPT_HISTORY_KEY = 'inku-batch-prompt-history';
	const BATCH_PROMPT_HISTORY_LIMIT = 20;

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
		liveMs: number;
		batchFailureReport: BatchFailureReport | null;
		canSubmit: boolean;
		error: string | null;
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
		liveMs,
		batchFailureReport,
		canSubmit,
		error,
		onSubmit,
		onStop,
	}: Props = $props();

	let batchTextareaEl = $state<HTMLTextAreaElement | null>(null);
	let batchScrollTop = $state(0);
	let batchPromptHistory = $state<string[]>([]);
	let selectedHistoryPrompt = $state('');
	const displayLineNumbersText = $derived(batchInput.trim() ? lineNumbersText : t().batchPlaceholder.split('\n').map((_, i) => String(i + 1)).join('\n'));
	const batchActiveLineStyle = $derived(
		batchActiveLine === null
			? ''
			: `--batch-active-top: ${9 + (batchActiveLine - 1) * 21.45 - batchScrollTop}px`
	);

	function normalizePrompt(text: string): string {
		return text.trim().replace(/\r\n/g, '\n');
	}

	function loadPromptHistory() {
		try {
			const parsed = JSON.parse(localStorage.getItem(BATCH_PROMPT_HISTORY_KEY) ?? '[]');
			if (!Array.isArray(parsed)) return;
			batchPromptHistory = parsed
				.filter((item): item is string => typeof item === 'string' && item.trim().length > 0)
				.slice(0, BATCH_PROMPT_HISTORY_LIMIT);
		} catch {
			batchPromptHistory = [];
		}
	}

	function savePromptHistory(nextHistory: string[]) {
		batchPromptHistory = nextHistory.slice(0, BATCH_PROMPT_HISTORY_LIMIT);
		try {
			localStorage.setItem(BATCH_PROMPT_HISTORY_KEY, JSON.stringify(batchPromptHistory));
		} catch {
			// localStorage failure should not block drawing.
		}
	}

	function rememberCurrentPrompt() {
		const prompt = normalizePrompt(batchInput);
		if (!prompt) return;
		savePromptHistory([prompt, ...batchPromptHistory.filter((item) => item !== prompt)]);
	}

	function restoreSelectedHistoryPrompt() {
		if (!selectedHistoryPrompt || batchRunning) return;
		batchInput = selectedHistoryPrompt;
	}

	function submitAndRemember() {
		rememberCurrentPrompt();
		void onSubmit();
	}

	onMount(loadPromptHistory);
</script>

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
			onscroll={() => (batchScrollTop = batchTextareaEl?.scrollTop ?? 0)}
		></textarea>
	</div>
</div>
{#if batchNonEmpty > 0}<p class="batch-info">{t().batchCount(batchNonEmpty)}</p>{/if}
{#if !batchRunning}
	<div class="batch-tools">
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
	<div class="batch-progress">
		<span>{t().batchProgress(batchCurrent, batchTotal)}</span>
		<span class="progress-time">{(liveMs / 1000).toFixed(1)}s</span>
		<button class="stop-sm" onclick={onStop}>{t().stopBtn}</button>
	</div>
{:else}
	<button class="play-btn" onclick={submitAndRemember} disabled={!canSubmit}>▶ <span>{t().submitBtn}</span></button>
{/if}

{#if error}<p class="error-text">{error}</p>{/if}
{#if batchRunning}
	<div class="batch-observe">
		<div class="batch-observe-head">
			<span>{t().batchActiveDdlLabel}</span>
			{#if batchActiveLine !== null}<span>{t().batchActiveLine(batchActiveLine)}</span>{/if}
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
	}
	.batch-ta:focus { border-color: var(--accent); }
	.batch-ta:read-only {
		color: var(--fg2);
		cursor: default;
	}
	.batch-ta-wrap {
		position: relative;
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
	.batch-progress {
		display: flex; align-items: center; gap: 8px; flex-wrap: wrap;
		padding: 8px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); font-size: 12px; color: var(--fg2);
		margin-top: 8px;
	}
	.progress-time { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.stop-sm {
		padding: 2px 7px; border: 1px solid var(--border2);
		border-radius: var(--r); background: none;
		color: var(--fg2); font-size: 11px; cursor: pointer; font-family: inherit;
	}
	.play-btn {
		width: 100%; margin-top: 8px; padding: 9px;
		font-size: 14px; font-weight: 500;
		background: var(--action-bg); color: var(--action-fg);
		border: none; border-radius: var(--r);
		letter-spacing: 0.08em; cursor: pointer;
		display: flex; align-items: center; justify-content: center; gap: 8px;
		font-family: inherit; transition: background 0.15s;
	}
	.play-btn:hover:not(:disabled) { background: var(--action-hover); }
	.play-btn:disabled {
		background: var(--action-disabled-bg);
		color: var(--action-disabled-fg);
		cursor: not-allowed;
	}
	.error-text { color: #a2342a; font-size: 12px; }
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
		color: #a2342a;
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
		display: flex;
		align-items: center;
		justify-content: space-between;
		gap: 8px;
		padding: 6px 9px;
		border-bottom: 1px solid #d9dfd1;
		color: #4a5b38;
		font-size: 11px;
		font-weight: 600;
	}
	.batch-observe-head span:last-child {
		color: var(--fg3);
		font-weight: 400;
		font-variant-numeric: tabular-nums;
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
	.batch-observe-body :global(.ddl-token) {
		border-radius: 2px;
		font-weight: inherit;
	}
	.batch-observe-body :global(.ddl-token-shape) { color: #2c5fb8; background: rgba(44, 95, 184, 0.08); }
	.batch-observe-body :global(.ddl-token-touch) { color: #7a5b2f; background: rgba(122, 91, 47, 0.10); }
	.batch-observe-body :global(.ddl-token-line) { color: #53606b; background: rgba(83, 96, 107, 0.10); }
	.batch-observe-body :global(.ddl-token-color) { color: #b12a6b; background: rgba(177, 42, 107, 0.09); }
	.batch-observe-body :global(.ddl-token-motion) { color: #197a74; background: rgba(25, 122, 116, 0.10); }
	.batch-observe-body :global(.ddl-token-place) { color: #6b4cb3; background: rgba(107, 76, 179, 0.09); }
	.batch-observe-body :global(.ddl-token-action) { color: #9a4a1d; background: rgba(154, 74, 29, 0.10); }
	.batch-observe-body :global(.ddl-token-angle) { color: #3d6f2c; background: rgba(61, 111, 44, 0.10); }
	.batch-observe-body :global(.ddl-token-ratio) { color: #9a3d3d; background: rgba(154, 61, 61, 0.09); }
	.batch-observe-body :global(.ddl-token-word) { color: #2c3e91; background: rgba(44, 62, 145, 0.08); }
	.batch-observe-body :global(.ddl-token-emotion) {
		color: #9b7a66;
		font-style: inherit;
	}
</style>
