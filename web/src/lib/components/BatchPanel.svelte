<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';

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
		batchActiveTokensIn: number | null;
		batchActiveTokensOut: number | null;
		batchTokensInTotal: number;
		batchTokensOutTotal: number;
		liveMs: number;
		batchFailureReport: BatchFailureReport | null;
		canSubmit: boolean;
		error: string | null;
		batchPromptHistory: string[];
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
		batchActiveTokensIn,
		batchActiveTokensOut,
		batchTokensInTotal,
		batchTokensOutTotal,
		liveMs,
		batchFailureReport,
		canSubmit,
		error,
		batchPromptHistory,
		onRememberBatchPrompt,
		onSubmit,
		onStop,
	}: Props = $props();

	let batchTextareaEl = $state<HTMLTextAreaElement | null>(null);
	let batchScrollTop = $state(0);
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
		<svg class="batch-crab" viewBox="0 0 74 42" aria-hidden="true">
			<g class="crab-walk">
				<ellipse class="crab-sand" cx="37" cy="35" rx="20" ry="3.5" />
				<g class="crab-bow">
					<g class="crab-bury">
						<path class="crab-leg leg-a" d="M23 28 L14 34 M28 29 L22 37 M46 29 L52 37 M51 28 L60 34" />
						<ellipse class="crab-body" cx="37" cy="24" rx="18" ry="11" />
						<path class="crab-shell" d="M23 23 Q37 9 51 23" />
						<g class="crab-claw claw-left">
							<path d="M21 23 C10 18 9 10 16 8" />
							<path class="claw-pincer" d="M15 8 C9 4 10 14 16 12 C21 16 22 6 15 8 Z" />
						</g>
						<g class="crab-claw claw-right">
							<path d="M53 23 C64 18 65 10 58 8" />
							<path class="claw-pincer" d="M59 8 C65 4 64 14 58 12 C53 16 52 6 59 8 Z" />
						</g>
						<g class="crab-eyes">
							<path d="M31 15 L29 8 M43 15 L45 8" />
							<circle class="eye-white" cx="29" cy="7" r="3.3" />
							<circle class="eye-white" cx="45" cy="7" r="3.3" />
							<circle class="eye-dot eye-left" cx="29" cy="7" r="1.2" />
							<circle class="eye-dot eye-right" cx="45" cy="7" r="1.2" />
						</g>
						<path class="crab-mouth" d="M33 25 Q37 28 41 25" />
					</g>
				</g>
			</g>
		</svg>
		<span>{t().batchProgress(batchCurrent, batchTotal)}</span>
		<span class="batch-token-total">{t().batchTokenTotal(batchTokensInTotal, batchTokensOutTotal)}</span>
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
			<div class="batch-observe-meta">
				{#if batchActiveLine !== null}<span>{t().batchActiveLine(batchActiveLine)}</span>{/if}
				<span>{t().batchTokenLine(batchActiveTokensIn, batchActiveTokensOut)}</span>
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
	.batch-crab {
		width: 46px;
		height: 28px;
		flex: 0 0 46px;
		overflow: visible;
	}
	.crab-sand {
		fill: #cbb48a;
		opacity: 0.45;
		animation: crabSand 7.8s ease-in-out infinite;
	}
	.crab-walk {
		transform-origin: 37px 24px;
		animation: crabWalk 6.8s ease-in-out infinite;
	}
	.crab-bow {
		transform-origin: 37px 30px;
		animation: crabBow 8.4s ease-in-out infinite;
	}
	.crab-bury {
		transform-origin: 37px 34px;
		animation: crabBury 7.8s ease-in-out infinite;
	}
	.crab-body {
		fill: #c75b43;
		stroke: #7e2d24;
		stroke-width: 2;
	}
	.crab-shell,
	.crab-mouth {
		fill: none;
		stroke: #7e2d24;
		stroke-width: 1.8;
		stroke-linecap: round;
	}
	.crab-leg,
	.crab-claw path,
	.crab-eyes path {
		fill: none;
		stroke: #7e2d24;
		stroke-width: 2.4;
		stroke-linecap: round;
		stroke-linejoin: round;
	}
	.leg-a { animation: crabLegs 0.72s ease-in-out infinite; transform-origin: 37px 30px; }
	.crab-claw { transform-origin: 37px 24px; }
	.claw-left {
		animation: clawLeft 2.4s ease-in-out infinite;
		transform-origin: 18px 21px;
	}
	.claw-right {
		animation: clawRight 2.7s ease-in-out infinite;
		transform-origin: 56px 21px;
	}
	.claw-pincer {
		fill: #e07a52;
		stroke: #7e2d24;
		stroke-width: 1.8;
	}
	.eye-white {
		fill: var(--panel);
		stroke: #7e2d24;
		stroke-width: 1.5;
	}
	.eye-dot {
		fill: #20201f;
		animation: crabEyes 1.9s steps(1, end) infinite;
	}
	.eye-right { animation-delay: 0.12s; }
	.progress-time { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
	.batch-token-total { font-size: 11px; color: var(--fg3); font-variant-numeric: tabular-nums; }
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
	.batch-observe-meta {
		display: flex;
		align-items: center;
		gap: 8px;
		color: var(--fg3);
		font-weight: 400;
		font-variant-numeric: tabular-nums;
	}
	.batch-observe-meta span {
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
	@keyframes crabWalk {
		0%, 100% { transform: translateX(-8px); }
		18% { transform: translateX(5px); }
		34% { transform: translateX(10px); }
		48% { transform: translateX(4px); }
		66% { transform: translateX(-7px); }
		84% { transform: translateX(-11px); }
	}
	@keyframes crabLegs {
		0%, 100% { transform: translateX(0); }
		50% { transform: translateX(1.6px); }
	}
	@keyframes clawLeft {
		0%, 18%, 54%, 100% { transform: rotate(0deg); }
		25%, 32% { transform: rotate(-24deg) translateY(-1px); }
		40% { transform: rotate(7deg); }
	}
	@keyframes clawRight {
		0%, 28%, 62%, 100% { transform: rotate(0deg); }
		36%, 44% { transform: rotate(25deg) translateY(-1px); }
		52% { transform: rotate(-7deg); }
	}
	@keyframes crabEyes {
		0%, 100% { transform: translateX(0); }
		22% { transform: translateX(-1.3px); }
		44% { transform: translateX(1.3px); }
		68% { transform: translateY(1px); }
	}
	@keyframes crabBury {
		0%, 56%, 100% { transform: translateY(0); opacity: 1; }
		67%, 72% { transform: translateY(9px); opacity: 0.62; }
		80% { transform: translateY(2px); opacity: 1; }
	}
	@keyframes crabSand {
		0%, 58%, 100% { transform: scaleX(1); opacity: 0.45; }
		68%, 76% { transform: scaleX(1.35); opacity: 0.72; }
	}
	@keyframes crabBow {
		0%, 42%, 88%, 100% { transform: rotate(0deg); }
		48%, 56% { transform: rotate(7deg) translateY(2px); }
		62% { transform: rotate(-3deg); }
	}
</style>
