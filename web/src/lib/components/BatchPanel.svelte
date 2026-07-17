<script lang="ts">
	import { t } from '$lib/i18n/index.svelte';
	import PaintButton from './PaintButton.svelte';
	import StopButton from './StopButton.svelte';

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
	<div class="batch-progress">
		{#if showCrab}
			<svg class="batch-crab" viewBox="0 0 74 42" aria-hidden="true">
				<defs>
					<clipPath id="crab-visible-clip">
						<rect x="0" y="0" width="74" height="80">
							<animate
								attributeName="height"
								dur="12.5s"
								repeatCount="indefinite"
								values="80;80;35;35;80;80"
								keyTimes="0;0.56;0.62;0.76;0.84;1"
							/>
						</rect>
					</clipPath>
				</defs>
				<g class="crab-walk">
					<g class="crab-water crab-water-back">
						<ellipse cx="37" cy="35" rx="21" ry="3.8" />
						<path d="M15 35 Q21 32.5 27 35 T39 35 T51 35 T63 35" />
					</g>
					<g class="crab-bow">
						<g class="crab-bury" clip-path="url(#crab-visible-clip)">
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
					<g class="crab-bubbles">
						<circle class="bubble bubble-a" cx="49" cy="32" r="1.7" />
						<circle class="bubble bubble-b" cx="55" cy="31" r="1.2" />
						<circle class="bubble bubble-c" cx="44" cy="33" r="0.9" />
					</g>
					<g class="crab-water crab-water-front">
						<ellipse cx="37" cy="35" rx="23" ry="4.3" />
						<path d="M14 35 Q20 32 26 35 T38 35 T50 35 T62 35" />
					</g>
				</g>
			</svg>
		{/if}
		<div class="batch-progress-table">
			<div class="batch-progress-row">
				<span class="batch-progress-key">{t().statsProgress}</span>
				<span class="batch-progress-value">{t().batchProgress(batchCurrent, batchTotal)}</span>
			</div>
			<div class="batch-progress-row">
				<span class="batch-progress-key">{t().statsTotal}</span>
				<span class="batch-progress-value">
					<span><span class="batch-metric-label">{t().statsElapsed}</span>{(liveMs / 1000).toFixed(1)}s</span>
					<span><span class="batch-metric-label">{t().statsTokens}</span>{tokenPair(batchTokensInTotal, batchTokensOutTotal)}</span>
				</span>
			</div>
		</div>
		<StopButton onclick={onStop}>{t().stopBtn}</StopButton>
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
	.batch-progress {
		display: flex; align-items: center; gap: 8px;
		padding: 8px 10px;
		border: 1px solid var(--border2); border-radius: var(--r);
		background: var(--panel); font-size: 12px; color: var(--fg2);
		margin-top: 8px;
		min-width: 0;
	}
	.batch-progress :global(.stop-btn) {
		margin-left: auto;
		flex: 0 0 auto;
	}
	.batch-crab {
		width: 46px;
		height: 28px;
		flex: 0 0 46px;
		overflow: visible;
	}
	.crab-water {
		opacity: 0;
		transform-origin: 37px 35px;
		animation: crabWater 12.5s ease-in-out infinite;
	}
	.crab-water ellipse {
		fill: rgba(77, 159, 190, 0.23);
	}
	.crab-water path {
		fill: none;
		stroke: rgba(66, 137, 171, 0.82);
		stroke-width: 1.6;
		stroke-linecap: round;
	}
	.crab-water-back {
		opacity: 0;
	}
	.crab-water-front {
		opacity: 0;
		animation-name: crabWaterFront;
	}
	.crab-walk {
		transform-origin: 37px 24px;
		animation: crabWalk 12s ease-in-out infinite;
	}
	.crab-bow {
		transform-origin: 37px 30px;
		animation: crabBow 14s ease-in-out infinite;
	}
	.crab-bury {
		transform-origin: 37px 34px;
		animation: crabBury 12.5s ease-in-out infinite;
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
	.leg-a { animation: crabLegs 1.25s ease-in-out infinite; transform-origin: 37px 30px; }
	.crab-claw { transform-origin: 37px 24px; }
	.claw-left {
		animation: clawLeft 8s ease-in-out infinite;
		transform-origin: 18px 21px;
	}
	.claw-right {
		animation: clawRight 9s ease-in-out infinite;
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
		animation: crabEyes 3.6s steps(1, end) infinite;
	}
	.eye-right { animation-delay: 0.12s; }
	.crab-bubbles {
		fill: none;
		stroke: #87bcd0;
		stroke-width: 1.3;
		opacity: 0;
		animation: crabBubbleGroup 12.5s ease-in-out infinite;
	}
	.bubble {
		transform-origin: 49px 35px;
		animation: crabBubble 12.5s ease-in-out infinite;
	}
	.bubble-b { animation-delay: 0.28s; }
	.bubble-c { animation-delay: 0.55s; }
	.batch-progress-table {
		display: grid;
		gap: 4px;
		flex: 1 1 auto;
		min-width: 0;
	}
	.batch-progress-row {
		display: grid;
		grid-template-columns: minmax(48px, 0.45fr) minmax(0, 1.55fr);
		gap: 8px;
		align-items: center;
		min-width: 0;
	}
	.batch-progress-key {
		color: var(--fg3);
		min-width: 0;
	}
	.batch-progress-value {
		display: grid;
		grid-template-columns: minmax(86px, 1fr) minmax(100px, 1.1fr);
		gap: 6px 10px;
		min-width: 0;
		font-variant-numeric: tabular-nums;
	}
	.batch-progress-row:first-child .batch-progress-value {
		display: block;
	}
	.batch-progress-value > span {
		min-width: 0;
		white-space: nowrap;
	}
	.batch-metric-label {
		display: inline-block;
		min-width: 3.9em;
		margin-right: 5px;
		color: var(--fg3);
		font-variant-numeric: normal;
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
	.batch-observe-body :global(.ddl-token-plugin) { color: #9f4b3b; background: rgba(185, 88, 69, 0.10); }
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
		0%, 18%, 46%, 66%, 100% { transform: rotate(0deg); }
		24%, 29% { transform: rotate(-18deg) translateY(-1px); }
		34% { transform: rotate(8deg); }
		52% { transform: rotate(-28deg) translateY(-2px); }
		56% { transform: rotate(14deg) translateY(1px); }
		60% { transform: rotate(-22deg) translateY(-1px); }
	}
	@keyframes clawRight {
		0%, 26%, 52%, 74%, 100% { transform: rotate(0deg); }
		34%, 40% { transform: rotate(20deg) translateY(-1px); }
		46% { transform: rotate(-8deg); }
		58% { transform: rotate(30deg) translateY(-2px); }
		62% { transform: rotate(-12deg) translateY(1px); }
		67% { transform: rotate(24deg) translateY(-1px); }
	}
	@keyframes crabEyes {
		0%, 100% { transform: translateX(0); }
		22% { transform: translateX(-1.3px); }
		44% { transform: translateX(1.3px); }
		68% { transform: translateY(1px); }
	}
	@keyframes crabBury {
		0%, 50%, 100% { transform: translateY(0); opacity: 1; }
		62%, 72% { transform: translateY(36px); opacity: 1; }
		82% { transform: translateY(6px); opacity: 1; }
	}
	@keyframes crabWater {
		0%, 56%, 88%, 100% { transform: scaleX(0.78); opacity: 0; }
		60% { transform: scaleX(1.02); opacity: 0.18; }
		66%, 78% { transform: scaleX(1.28); opacity: 0.62; }
		84% { transform: scaleX(1.00); opacity: 0.12; }
	}
	@keyframes crabWaterFront {
		0%, 56%, 88%, 100% { transform: scaleX(0.74); opacity: 0; }
		62% { transform: scaleX(1.14); opacity: 0.42; }
		68%, 78% { transform: scaleX(1.34); opacity: 0.76; }
		84% { transform: scaleX(1.04); opacity: 0.18; }
	}
	@keyframes crabBow {
		0%, 42%, 88%, 100% { transform: rotate(0deg); }
		48%, 56% { transform: rotate(7deg) translateY(2px); }
		62% { transform: rotate(-3deg); }
	}
	@keyframes crabBubbleGroup {
		0%, 58%, 88%, 100% { opacity: 0; }
		64%, 82% { opacity: 0.9; }
	}
	@keyframes crabBubble {
		0%, 58%, 88%, 100% { transform: translate(0, 0) scale(0.72); opacity: 0; }
		64% { transform: translate(0, 0) scale(0.82); opacity: 0.85; }
		74% { transform: translate(2px, -9px) scale(1.05); opacity: 0.58; }
		84% { transform: translate(4px, -18px) scale(1.24); opacity: 0; }
	}
</style>
